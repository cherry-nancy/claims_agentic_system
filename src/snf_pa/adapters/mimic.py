"""Assemble CaseBundles from the Parquet subset (design v8 §3.1-3.6).

    uv run python -m snf_pa.adapters.mimic dev        # -> data/sample/case_bundles/dev/<hadm_id>.json

Only `hadm_id` and `subject_id` are read from the sample file. Its other columns (discharge location, scenario,
need tags) are post-discharge or label information and never enter a bundle (hard rules 2 and 10, D-006).
The test split is not built here; it is built only when the user starts the formal evaluation (hard rule 3).
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

import duckdb

from snf_pa.adapters import timeline as tl
from snf_pa.adapters.sources import discharge_note, facts, radiology
from snf_pa.paths import ROOT, sql_path
from snf_pa.registry import load_needs, load_sources
from snf_pa.schemas import CaseBundle, PriorStay

PARQUET = ROOT / "data" / "derived" / "parquet"
SPLITS = ROOT / "data" / "splits"
OUT = ROOT / "data" / "sample" / "case_bundles"

ASSUMED = {  # data MIMIC cannot provide (design §3.3, hard rule 4)
    "C2": "assume_snf_admission_within_30_days_of_discharge",
    "C7": "assume_physician_certification_submitted",
    "C8": "assume_benefit_days_available",
}


def _module_hash(mod) -> str:
    return hashlib.sha256(Path(mod.__file__).read_bytes().replace(b"\r\n", b"\n")).hexdigest()[:12]


def case_ids(split: str) -> list[tuple[int, int]]:
    with (SPLITS / f"{split}_cases.csv").open(encoding="utf-8") as f:
        return [(int(r["hadm_id"]), int(r["subject_id"])) for r in csv.DictReader(f)]


def build(split: str, out_dir: Path | None = None) -> list[CaseBundle]:
    if split != "dev":
        raise SystemExit("only the dev split is built during development (CLAUDE.md hard rule 3)")
    cases = case_ids(split)
    out_dir = out_dir or OUT / split
    out_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    tl.register_parquet(con)
    subj = ",".join(str(s) for _, s in cases)
    con.execute(f"create temp table subj_adm as select hadm_id from admissions where subject_id in ({subj})")
    tl.build_timeline(con, "subj_adm")
    tl.prior_stays(con)
    hadms = ",".join(str(h) for h, _ in cases)
    con.execute(f"create temp table case_tl as select * from timeline where hadm_id in ({hadms})")
    cat, reg = load_needs(), load_sources()
    poe_ev = facts.poe_facts(con, PARQUET / "poe.parquet", cat)
    rx_ev = facts.rx_facts(con, PARQUET / "prescriptions.parquet", cat)
    versions = {s.id: f"registry-v{reg.version}-{reg.content_hash}" for s in reg.sources}
    versions["discharge_note"] += f"+code-{_module_hash(discharge_note)}"
    versions["needs_catalog"] = f"v{cat.version}-{cat.content_hash}"

    demo = {r[0]: r[1:] for r in con.execute(f"""
        select a.hadm_id, p.anchor_age + (year(a.admittime) - p.anchor_year), p.gender, a.insurance
        from admissions a join '{sql_path(PARQUET / 'patients.parquet')}' p using (subject_id)
        where a.hadm_id in ({hadms})""").fetchall()}
    notes = {r[0]: r[1:] for r in con.execute(f"""
        select hadm_id, note_id, text from '{sql_path(PARQUET / 'discharge.parquet')}' where hadm_id in ({hadms})
        qualify row_number() over (partition by hadm_id order by note_seq desc) = 1""").fetchall()}
    rads: dict[int, list] = {}
    for h, nid, text, st in con.execute(f"""
            select hadm_id, note_id, text, storetime::TIMESTAMP from '{sql_path(PARQUET / 'radiology.parquet')}'
            where hadm_id in ({hadms}) order by 4, note_id""").fetchall():
        rads.setdefault(h, []).append((nid, text, st))
    cols = [d[0] for d in con.execute("select * from case_tl limit 0").description]
    bundles = []
    for row in con.execute("select * from case_tl order by hadm_id").fetchall():
        t = dict(zip(cols, row))
        h = t["hadm_id"]
        prior = [PriorStay(hadm_id=p[0], admittime=p[1], dischtime=p[2], inpatient_start=p[3],
                           inpatient_start_source=p[4], midnights=p[5])
                 for p in con.execute("""select prior_hadm_id, admittime, dischtime, inpatient_start,
                     inpatient_start_source, midnights from prior_stays where hadm_id = ? order by dischtime""",
                                      [h]).fetchall()]
        missing = ["pt_ot_evaluation_note"]          # MIMIC has no therapy evaluation notes
        if t["inpatient_start_source"] == "admittime_fallback":
            missing.append("inpatient_admission_order")
        ev = []
        if h in notes:
            ev += discharge_note.to_evidence(notes[h][0], notes[h][1])[0]
        else:
            missing.append("discharge_summary")
        for nid, text, st in rads.get(h, []):
            ev += radiology.to_evidence(nid, text, st, t["t_pa"])
        ev += poe_ev.get(h, []) + rx_ev.get(h, [])
        age, sex, ins = demo[h]
        # time points that fall after T_pa are not known at T_pa: blank them (dischtime excepted, see schemas)
        tline = {k: (t[k] if t[k] is None or k == "dischtime" or t[k] <= t["t_pa"] else None)
                 for k in ("admittime", "dischtime", "ed_intime", "ed_outtime", "observation_order_time",
                           "inpatient_order_time", "inpatient_start")}
        b = CaseBundle(
            case_id=str(h),
            demographics={"age_at_admit": age, "sex": sex, "insurance": ins},
            timeline=tline | {"inpatient_start_source": t["inpatient_start_source"], "t_pa": t["t_pa"],
                              "prior_stays_30d": prior},
            evidence=ev, sources=versions, assumed=ASSUMED, missing=missing,
        ).sealed()
        (out_dir / f"{h}.json").write_text(json.dumps(b.model_dump(mode="json"), indent=1, ensure_ascii=False) + "\n",
                                           encoding="utf-8", newline="\n")
        bundles.append(b)
    return bundles


if __name__ == "__main__":
    bs = build(sys.argv[1] if len(sys.argv) > 1 else "dev")
    n_ev = [len(b.evidence) for b in bs]
    print(f"{len(bs)} bundles; evidence per case min/median/max = {min(n_ev)}/{sorted(n_ev)[len(n_ev)//2]}/{max(n_ev)}")
