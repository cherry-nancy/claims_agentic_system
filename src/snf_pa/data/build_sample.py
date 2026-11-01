"""Build the 50-case Step 1 sample.

Run from the project root:
    $env:PYTHONPATH = "src"; uv run python -m snf_pa.data.build_sample

Outputs go to data/sample/ (gitignored). Only aggregate counts are printed.
"""
import json
from datetime import datetime, timezone

from . import config as C
from . import cohort


def main() -> None:
    C.SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    con = cohort.connect()

    cohort.build_candidates(con)
    counts = cohort.candidate_counts(con)
    quotas = cohort.draw_sample(con)

    sample_pq = C.SAMPLE_DIR / "sample_cases.parquet"
    sample_csv = C.SAMPLE_DIR / "sample_cases.csv"
    con.execute(f"copy sample to '{C.sql_path(sample_pq)}' (format parquet)")
    con.execute(f"copy sample to '{C.sql_path(sample_csv)}' (header, delimiter ',')")

    counts_csv = C.SAMPLE_DIR / "candidate_counts.csv"
    counts_csv.write_text(
        "category,discharge_location,n_eligible_admissions,n_patients\n"
        + "\n".join(",".join(map(str, r)) for r in counts) + "\n",
        encoding="utf-8",
    )

    n_notes = cohort.export_notes(con, C.SAMPLE_DIR / "notes_raw.parquet")

    by_cell = con.execute(
        "select category, discharge_location, split, count(*) from sample group by all order by all"
    ).fetchall()
    n = con.execute("select count(*) from sample").fetchall()[0][0]
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seed": C.SEED,
        "n_cases": n,
        "n_notes": n_notes,
        "criteria": {
            "insurance": "Medicare",
            "min_age_at_admit": C.MIN_AGE,
            "min_inpatient_midnights": C.MIN_MIDNIGHTS,
            "excluded": [
                "in-hospital deaths",
                "admission_type containing OBSERVATION",
                "any stay that passed through the 'Observation' care unit",
                "admissions without a discharge summary",
            ],
            "label": "label_snf=1 if discharge_location is SKILLED NURSING FACILITY (silver label, not a payer decision)",
            "negatives": "HOME HEALTH CARE and HOME with >=3 midnights, same diagnosis category",
            "one_admission_per_patient": True,
            "category_source": "primary diagnosis (seq_num=1), ICD-9/10; joint_replacement via procedure codes",
        },
        "target_quotas_per_category": C.LOCATION_QUOTAS,
        "effective_quotas": [
            {"category": c, "discharge_location": loc, "n": q_} for (c, loc), q_ in quotas.items()
        ],
        "split_rule": f"rank within cell by hash; position % {C.TEST_MODULUS} in {list(C.TEST_POSITIONS)} -> test",
        "batch_rule": f"batch 1 = first {sum(C.BATCH1_QUOTAS.values())} per category-cell prefix (original 50 cases), rest batch 2",
        "cells": [dict(zip(["category", "discharge_location", "split", "n"], r)) for r in by_cell],
        "files": ["sample_cases.parquet", "sample_cases.csv", "candidate_counts.csv", "notes_raw.parquet"],
        "note": "notes_raw.parquet holds raw MIMIC text: keep local, never print or upload.",
    }
    (C.SAMPLE_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"sample cases: {n}; notes exported: {n_notes}")
    print("eligible pool (category | discharge_location | admissions | patients):")
    for r in counts:
        print("  ", *r, sep=" | ")
    print("sample cells (category | location | split | n):")
    for r in by_cell:
        print("  ", *r, sep=" | ")
    print(f"written to {C.SAMPLE_DIR}")


if __name__ == "__main__":
    main()
