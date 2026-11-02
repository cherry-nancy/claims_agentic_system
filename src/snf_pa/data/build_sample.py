"""Step 1 entry point: PYTHONPATH=src uv run python -m snf_pa.data.build_sample

Writes data/sample/ (gitignored). Prints counts only, never note text.
"""
import json
from datetime import date

import polars as pl

from snf_pa.data import cohort
from snf_pa.data import config as C

COLUMNS = [
    "subject_id", "hadm_id", "note_id", "category", "discharge_location", "label_snf", "batch", "split",
    "age_at_admit", "gender", "race", "language", "admission_type", "admission_location", "admittime",
    "dischtime", "inpatient_midnights", "los_days", "icu_any", "first_dx_code", "first_dx_version",
    "first_dx_title",
]


def n_test(n: int) -> int:
    return 0 if n < 2 else max(1, round(n * C.TEST_FRACTION))


def draw_category(con, category: str) -> pl.DataFrame:
    want = dict(C.QUOTAS[2])
    avail = {loc: len(cohort.draw(con, category, loc, 10**6)) for loc in want}
    # Too few HOME cases (hip fracture): fill the gap with HOME HEALTH CARE so each category stays at 60.
    short = max(0, want["HOME"] - avail["HOME"])
    want["HOME"] -= short
    want["HOME HEALTH CARE"] += short
    parts = []
    for loc, k in want.items():
        if avail[loc] < k:
            raise ValueError(f"{category}/{loc}: need {k}, only {avail[loc]} candidates")
        df = cohort.draw(con, category, loc, k).with_columns(
            batch=pl.when(pl.col("stratum_rank") <= C.QUOTAS[1][loc]).then(1).otherwise(2)
        )
        for b in (1, 2):
            part = df.filter(pl.col("batch") == b).sort("stratum_rank")
            t = n_test(len(part))
            split = ["dev"] * (len(part) - t) + ["test"] * t
            parts.append(part.with_columns(split=pl.Series(split, dtype=pl.String)))
    return pl.concat(parts)


def main() -> None:
    C.SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    con = cohort.connect()
    print("building candidate pool (scans the 1.1 GB note file)...")
    cohort.build_candidates(con)

    counts = cohort.candidate_counts(con)
    counts.write_csv(C.SAMPLE_DIR / "candidate_counts.csv")

    sample = pl.concat([draw_category(con, cat) for cat in C.CATEGORIES]).select(COLUMNS).sort("hadm_id")
    sample.write_parquet(C.SAMPLE_DIR / "sample_cases.parquet")
    sample.write_csv(C.SAMPLE_DIR / "sample_cases.csv")

    print("exporting notes...")
    cohort.export_notes(con, sample["note_id"].cast(pl.String).to_list(), C.SAMPLE_DIR / "notes_raw.parquet")

    grid = sample.group_by("category", "discharge_location", "batch", "split").len().sort(pl.all())
    manifest = {
        "built": date.today().isoformat(),
        "seed": C.SEED,
        "n_cases": len(sample),
        "n_batch1": sample.filter(pl.col("batch") == 1).height,
        "inclusion": [
            "insurance = Medicare",
            f"age at admission >= {C.MIN_AGE}",
            "alive at discharge (hospital_expire_flag = 0)",
            f"inpatient midnights >= {C.MIN_MIDNIGHTS} (calendar dates admittime -> dischtime)",
            "admission_type not an observation type; never in the 'Observation' care unit",
            "discharge_location in SNF / HOME HEALTH CARE / HOME",
            "has a discharge summary >= 500 chars (latest note_seq kept)",
            "one admission per patient, chosen by seeded hash",
        ],
        "category_rule": "first-listed diagnosis (ICD-9/10); hip fracture first, then any hip/knee "
                         "replacement procedure, then stroke, heart failure, pneumonia/sepsis",
        "quotas_per_category": C.QUOTAS,
        "test_fraction": C.TEST_FRACTION,
        "mimic_root": C.sql_path(C.MIMIC_ROOT),
        "grid": grid.to_dicts(),
    }
    (C.SAMPLE_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")

    print(counts)
    print(sample.group_by("category", "discharge_location").len().sort(pl.all()))
    print(sample.group_by("batch", "split").len().sort(pl.all()))


if __name__ == "__main__":
    main()
