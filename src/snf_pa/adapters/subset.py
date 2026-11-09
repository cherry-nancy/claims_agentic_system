"""Parquet subset of the raw tables for the candidate pool's patients (design §3.1 note 2).

    uv run python -m snf_pa.adapters.subset

Filter: subject_id in the candidate pool (data/derived/cohort/pool.parquet). All admissions of those patients
are kept, not only pool admissions, so the rule engine can look for a qualifying prior stay (§6.2).
No T_pa truncation here: the adapter truncates at T_pa (§3.1 note 6), so every timestamp is kept.

Table whitelist (user decision 2026-11-08): only the tables the design uses (timeline §3.4, fact cards §3.6,
notes §3.5, A0 features §10.2). labevents, chartevents, emar, pharmacy, inputevents are not built. All
columns of the listed tables are kept (they are small once filtered; the column whitelist in §3.1 was aimed
at the big tables we skip).

Read-only on MIMIC_RAW_DIR; writes data/derived/parquet/ (not in git) and a manifest with row counts.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

import duckdb

from snf_pa.adapters.cohort import NOTE_COLUMNS
from snf_pa.paths import ROOT, raw_table, sql_path

POOL = ROOT / "data" / "derived" / "cohort" / "pool.parquet"
OUT = ROOT / "data" / "derived" / "parquet"

# name -> (raw table, extra read_csv options). Types are sniffed over the whole file (sample_size=-1) so a
# late value such as an ICD-10 code with letters cannot break a type guessed from the first rows.
TABLES: dict[str, tuple[str, str]] = {
    "admissions": ("mimiciv-3.1/hosp/admissions", ""),
    "patients": ("mimiciv-3.1/hosp/patients", ""),
    "transfers": ("mimiciv-3.1/hosp/transfers", ""),
    "services": ("mimiciv-3.1/hosp/services", ""),
    "diagnoses_icd": ("mimiciv-3.1/hosp/diagnoses_icd", ", types={'icd_code':'VARCHAR'}"),
    "procedures_icd": ("mimiciv-3.1/hosp/procedures_icd", ", types={'icd_code':'VARCHAR'}"),
    "drgcodes": ("mimiciv-3.1/hosp/drgcodes", ", types={'drg_code':'VARCHAR'}"),
    "poe": ("mimiciv-3.1/hosp/poe", ""),
    "poe_detail": ("mimiciv-3.1/hosp/poe_detail", ""),
    "prescriptions": ("mimiciv-3.1/hosp/prescriptions", ""),
    "icustays": ("mimiciv-3.1/icu/icustays", ""),
    "edstays": ("mimic-iv-ed/ed/edstays", ""),
    "discharge": ("mimic-iv-note/note/discharge", f", columns={NOTE_COLUMNS}"),
    "radiology": ("mimic-iv-note/note/radiology", f", columns={NOTE_COLUMNS}"),
}


def build(only: list[str] | None = None) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"create temp table pool_subjects as select distinct subject_id from '{sql_path(POOL)}'")
    n_subjects = con.execute("select count(*) from pool_subjects").fetchall()[0][0]
    manifest_path = OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"tables": {}}
    manifest.update({"filter": "subject_id in candidate pool", "pool": "data/derived/cohort/pool.parquet",
                     "n_pool_subjects": n_subjects})
    for name, (table, opts) in TABLES.items():
        if only and name not in only:
            continue
        src = raw_table(table)
        dst = OUT / f"{name}.parquet"
        t0 = time.time()
        sniff = "" if "columns=" in opts else ", sample_size=-1"
        con.execute(f"""
            copy (select r.* from read_csv('{sql_path(src)}', header=true{sniff}{opts}) r
                  semi join pool_subjects p using (subject_id))
            to '{sql_path(dst)}' (format parquet, compression zstd)
        """)
        rows = con.execute(f"select count(*) from '{sql_path(dst)}'").fetchall()[0][0]
        cols = [r[0] for r in con.execute(f"describe select * from '{sql_path(dst)}'").fetchall()]
        manifest["tables"][name] = {
            "source": str(src), "source_bytes": src.stat().st_size, "rows": rows, "columns": cols,
            "parquet_bytes": dst.stat().st_size, "seconds": round(time.time() - t0, 1),
        }
        print(f"{name:15s} rows={rows:>10,} cols={len(cols):>2} {dst.stat().st_size / 1e6:8.1f} MB "
              f"{time.time() - t0:6.1f}s", flush=True)
    manifest["built_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    import sys
    build(sys.argv[1:] or None)
