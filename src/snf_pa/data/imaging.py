"""Imaging test: replace the discharge summary's imaging impressions with the reports available at T_pa.

Run from the project root (after snf_pa.data.redact and snf_pa.data.leakage, whose pool it reuses):
    PYTHONPATH=src uv run python -m snf_pa.data.imaging [--cutoff-hours 24]

T_pa is approximated as discharge time minus --cutoff-hours (default 24; rerun with 48 as the sensitivity check).
A radiology report counts as available if it was signed
(storetime; charttime if missing) by then; the scan time alone is not enough, since the report does not exist yet.

Which text is "the impression section"? Impressions are pasted into Pertinent Results mostly without an
"IMPRESSION:" label, and most labelled blocks there are not radiology (in the sample, 43% of the stays' radiology
impressions appear nearly verbatim in Pertinent Results, while labelled blocks share a median 4% of their words with
any report). So copied imaging text is found by content: a run of at least MIN_RUN words of Pertinent Results in
which every word belongs to a word 3-gram of one of the stay's radiology impressions.

1. Timed-imaging notes: the strict redacted note with those runs deleted, plus a section listing the impression of
   each radiology report of the stay signed before T_pa (exam, hospital day). Report text goes through the same
   clause rules as the note.
2. Comparison with the summary: how much copied imaging text comes from reports signed before T_pa ("before") or
   only from reports signed after it ("after": imaging a reviewer would not have had), and the share of reports
   available at T_pa that the summary does not quote (at least half of their 3-grams absent from Pertinent Results).
3. Leakage: the classifier of snf_pa.data.leakage, trained on the pool and tested on the sample, strict vs timed.

Writes data/sample/radiology_impressions.parquet (cut-off free), notes_timed_imaging_{h}h.parquet and
imaging_report_{h}h.json (gitignored).
Prints aggregate counts only, never note text.
"""
import argparse
import json
import re

import numpy as np
import polars as pl
from sklearn.metrics import roc_auc_score

from snf_pa.data import cohort
from snf_pa.data import config as C
from snf_pa.data.leakage import HOME, POOL_CASES, pool_frame, sample_frame, structured, text_model
from snf_pa.data.redact import SENTENCE_BREAK, Stats, delete, redact_sentence, sections

CUTOFF_HOURS = 24  # default; the plan's main rule, with 48 as the sensitivity check
MIN_RUN = 5  # words
QUOTED = 0.5  # share of a report's 3-grams found in Pertinent Results for the report to count as quoted
RAD = C.SAMPLE_DIR / "radiology_impressions.parquet"
HEADING = "Imaging Impressions (reports signed before T_pa):"

# In a radiology report: "IMPRESSION:" up to the next all-caps heading (NOTIFICATION:, ...) or the end.
RAD_IMPRESSION = re.compile(r"IMPRESSION:\s*(.*?)(?=\n[ \t]*[A-Z][A-Z ()/]{3,}:|\Z)", re.DOTALL)
WORD = re.compile(r"[A-Za-z0-9]+")


def trigrams(s: str) -> set[tuple[str, ...]]:
    w = [m[0].lower() for m in WORD.finditer(s)]
    return {tuple(w[i:i + 3]) for i in range(len(w) - 2)}


def load_radiology(cases: pl.DataFrame) -> pl.DataFrame:
    """Radiology reports of each stay (scan from a day before admission to discharge) with their impression."""
    con = cohort.connect()
    con.register("cases", cases.to_arrow())
    n = C.sql_path(C.NOTE)
    rad = con.sql(f"""
    with r as (
      select note_id, subject_id::VARCHAR as subject_id, note_type, charttime::TIMESTAMP as charttime,
             coalesce(storetime, charttime)::TIMESTAMP as signed, text
      from read_csv('{n}/radiology.csv.gz', header = true, quote = '"', escape = '"')
      where subject_id::VARCHAR in (select subject_id from cases)),
    ex as (
      select note_id, any_value(field_value) as exam
      from read_csv('{n}/radiology_detail.csv.gz', header = true, quote = '"', escape = '"')
      where field_name = 'exam_name' and note_id in (select note_id from r) group by note_id)
    select c.hadm_id, r.note_id, r.note_type, ex.exam, r.charttime, r.signed,
           date_diff('day', c.admittime::DATE, r.charttime::DATE) + 1 as hospital_day,
           c.dischtime::TIMESTAMP as dischtime, r.text
    from cases c
    join r on r.subject_id = c.subject_id
      and r.charttime between c.admittime::TIMESTAMP - interval 1 day and c.dischtime::TIMESTAMP
    left join ex using (note_id)
    order by c.hadm_id, r.charttime
    """).pl()
    imp = [m[1].strip() if (m := RAD_IMPRESSION.search(t)) else None for t in rad["text"]]
    return rad.with_columns(impression=pl.Series(imp, dtype=pl.String)).drop("text")


def clean(s: str) -> str:
    """One line, with the disposition clause rules applied."""
    st = Stats()
    s = "".join(redact_sentence(x, st) for x in re.split(f"({SENTENCE_BREAK.pattern})", s) if x)
    return re.sub(r"\s+", " ", s).strip()


def pertinent_results(text: str) -> tuple[int, int]:
    return next(((a, b) for h, a, b in sections(text) if h == "Pertinent Results"), (0, 0))


def copied_runs(text: str, reports: list[dict]) -> list[tuple[int, int, bool]]:
    """(start, end, from a report signed before T_pa) of imaging text in Pertinent Results copied from a report."""
    a, b = pertinent_results(text)
    toks = list(WORD.finditer(text, a, b))
    low = [m[0].lower() for m in toks]
    pre = set().union(*[trigrams(r["impression"]) for r in reports if r["before_cutoff"]])
    post = set().union(*[trigrams(r["impression"]) for r in reports if not r["before_cutoff"]])
    mark = [0] * len(toks)  # 0 none, 1 after only, 2 before
    for i in range(len(toks) - 2):
        g = tuple(low[i:i + 3])
        level = 2 if g in pre else 1 if g in post else 0
        for j in range(i, i + 3):
            mark[j] = max(mark[j], level)
    runs, i = [], 0
    while i < len(toks):
        if not mark[i]:
            i += 1
            continue
        j = i
        while j < len(toks) and mark[j]:
            j += 1
        if j - i >= MIN_RUN:
            runs.append((toks[i].start(), toks[j - 1].end(), 2 in mark[i:j]))
        i = j
    return runs


def timed(text: str, reports: list[dict]) -> str:
    body, _ = delete(text, list(range(len(text))), [(x, y) for x, y, _ in copied_runs(text, reports)])
    lines = [f"- {r['exam'] or 'Imaging'} (hospital day {r['hospital_day']}): {clean(r['impression'])}"
             for r in reports if r["before_cutoff"]]
    return re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", body).rstrip() + f"\n\n{HEADING}\n" + ("\n".join(lines) or "None.")


def compare(text: str, reports: list[dict]) -> dict:
    runs = copied_runs(text, reports)
    a, b = pertinent_results(text)
    pr = trigrams(text[a:b])
    pre = [trigrams(r["impression"]) for r in reports if r["before_cutoff"]]
    pre = [g for g in pre if g]
    return {"copied_chars_before": sum(y - x for x, y, before in runs if before),
            "copied_chars_after": sum(y - x for x, y, before in runs if not before),
            "n_reports_before": len(pre), "n_reports_quoted": sum(len(g & pr) / len(g) >= QUOTED for g in pre),
            "n_reports_after": sum(not r["before_cutoff"] for r in reports)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cutoff-hours", type=int, default=CUTOFF_HOURS)
    hours = ap.parse_args().cutoff_hours
    out_file = C.SAMPLE_DIR / f"notes_timed_imaging_{hours}h.parquet"
    report_file = C.SAMPLE_DIR / f"imaging_report_{hours}h.json"
    sample = sample_frame()
    times = pl.concat([pl.read_csv(C.SAMPLE_DIR / f"{f}.csv", infer_schema_length=0)
                       .select("subject_id", "hadm_id", "admittime", "dischtime")
                       for f in ["sample_cases1", "sample_cases1_supp"]])
    pool = pool_frame()
    con = cohort.connect()
    pool_ids = pl.read_parquet(POOL_CASES).select(pl.col("subject_id", "hadm_id").cast(pl.String))
    con.register("pool_ids", pool_ids.to_arrow())
    pool_times = con.sql(f"""
    select p.subject_id, p.hadm_id, a.admittime::VARCHAR as admittime, a.dischtime::VARCHAR as dischtime
    from read_csv_auto('{C.sql_path(C.HOSP)}/admissions.csv.gz') a
    join pool_ids p on p.hadm_id = a.hadm_id::VARCHAR""").pl()
    if not RAD.exists() or "dischtime" not in pl.read_parquet_schema(RAD):
        print("reading radiology reports (scans the radiology note file)...")
        load_radiology(pl.concat([times, pool_times])).write_parquet(RAD)
    rad = pl.read_parquet(RAD).filter(pl.col("impression").is_not_null()).with_columns(
        before_cutoff=pl.col("signed") <= pl.col("dischtime") - pl.duration(hours=hours))
    by_hadm = {k[0]: g.sort("charttime").to_dicts() for k, g in rad.group_by("hadm_id")}

    rows = []
    for name, d in [("sample", sample), ("pool", pool)]:
        for r in d.iter_rows(named=True):
            reps = by_hadm.get(r["hadm_id"], [])
            rows.append({"set": name, "hadm_id": r["hadm_id"], "timed": timed(r["strict"], reps),
                         **compare(r["strict"], reps)})
    out = pl.DataFrame(rows)
    out.write_parquet(out_file)

    # Comparison on the sample, by destination.
    s = out.filter(pl.col("set") == "sample").join(sample.select("hadm_id", "discharge_location"), on="hadm_id")
    comp = s.group_by("discharge_location").agg(
        pl.len().alias("notes"),
        (pl.col("n_reports_before") > 0).mean().round(2).alias("has_report_before"),
        (pl.col("copied_chars_before") + pl.col("copied_chars_after") > 0).mean().round(2).alias("ds_copies_imaging"),
        (pl.col("copied_chars_after") > 0).mean().round(2).alias("ds_copies_post_t_pa"),
        (pl.col("copied_chars_after").sum() / (pl.col("copied_chars_before") + pl.col("copied_chars_after")).sum())
        .round(2).alias("copied_share_post_t_pa"),
        pl.col("n_reports_before").sum().alias("reports_before"),
        (1 - pl.col("n_reports_quoted").sum() / pl.col("n_reports_before").sum()).round(2).alias("before_not_in_ds"),
        pl.col("n_reports_after").sum().alias("reports_after")).sort("discharge_location")

    # Leakage: strict vs timed, trained on the pool, tested on the sample (SNF vs home / home health).
    p = pool.join(out.filter(pl.col("set") == "pool").select("hadm_id", "timed"), on="hadm_id").with_columns(
        y=pl.col("label_snf").cast(pl.Int64))
    t = sample.join(out.filter(pl.col("set") == "sample").select("hadm_id", "timed"), on="hadm_id").filter(
        pl.col("discharge_location").is_in(["SKILLED NURSING FACILITY", *HOME])).with_columns(
        y=(pl.col("discharge_location") == "SKILLED NURSING FACILITY").cast(pl.Int64))
    auc = {"structured_only": round(roc_auc_score(t["y"], structured(p, t)), 3)}
    for col in ["strict", "timed"]:
        vec, lr = text_model(p[col].to_list(), p["y"].to_numpy())
        auc[col] = round(roc_auc_score(t["y"], lr.predict_proba(vec.transform(t[col].to_list()))[:, 1]), 3)

    sx = s.join(sample.select("hadm_id", "strict"), on="hadm_id")
    chars = {c: int(np.median([len(x) for x in sx[c]])) for c in ["strict", "timed"]}
    report = {"cutoff_hours": hours, "min_run_words": MIN_RUN, "quoted_threshold": QUOTED, "radiology_reports_with_impression": rad.height,
              "comparison_by_destination": comp.to_dicts(), "auc_snf_vs_home": auc, "median_chars": chars}
    report_file.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    with pl.Config(tbl_width_chars=220, tbl_cols=20):
        print(f"T_pa = discharge - {hours}h; {rad.height} radiology reports with an impression "
              f"(sample + pool stays)")
        print(comp)
    print("AUC SNF vs home/home health (train pool, test sample):", auc)
    print(f"-> {report_file.relative_to(C.ROOT)}")


if __name__ == "__main__":
    main()
