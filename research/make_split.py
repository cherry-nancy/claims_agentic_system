"""Split the candidate pool's patients into dev / test by subject_id (design §3.2, §10.1; CLAUDE.md rule 3).

    uv run python -m snf_pa.adapters.cohort      # builds data/derived/cohort/pool.parquet
    uv run python research/make_split.py         # writes data/splits/subjects.csv (+ .meta.json)

Rule: u = first 8 hex digits of sha256(f"{SALT}:{subject_id}") / 16**8; dev if u < DEV_FRACTION else test.
Deterministic on any machine. The split is decided per patient before any sampling, so later sampling changes
can never move a patient between dev and test.

Refuses to overwrite an existing split: once the user freezes it (tools/freeze.py) it must not change.
"""
from __future__ import annotations

import hashlib
import json
import sys

import duckdb

from snf_pa.paths import ROOT

SALT = "snf-pa-split-v1"
DEV_FRACTION = 0.5  # user decision 2026-11-08
POOL = ROOT / "data" / "derived" / "cohort" / "pool.parquet"
OUT = ROOT / "data" / "splits" / "subjects.csv"
META = ROOT / "data" / "splits" / "subjects.meta.json"


def assign(subject_id: int) -> str:
    u = int(hashlib.sha256(f"{SALT}:{subject_id}".encode()).hexdigest()[:8], 16) / 16**8
    return "dev" if u < DEV_FRACTION else "test"


def main() -> None:
    if OUT.exists() or META.exists():
        sys.exit(f"{OUT} already exists; the split is protected and is never regenerated.")
    if not POOL.exists():
        sys.exit(f"{POOL} missing; run `uv run python -m snf_pa.adapters.cohort` first.")
    subjects = [r[0] for r in duckdb.sql(
        f"select distinct subject_id from '{POOL.as_posix()}' order by subject_id").fetchall()]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="\n") as f:
        f.write("subject_id,split\n")
        for s in subjects:
            f.write(f"{s},{assign(s)}\n")
    n_dev = sum(assign(s) == "dev" for s in subjects)
    META.write_text(json.dumps({
        "rule": "sha256(f'{salt}:{subject_id}')[:8] / 16**8 < dev_fraction -> dev, else test",
        "salt": SALT, "dev_fraction": DEV_FRACTION,
        "source": "data/derived/cohort/pool.parquet (strict year rule 2011-2018, design §3.2)",
        "n_subjects": len(subjects), "n_dev": n_dev, "n_test": len(subjects) - n_dev,
    }, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {OUT}: {len(subjects)} subjects, dev {n_dev}, test {len(subjects) - n_dev}")


if __name__ == "__main__":
    main()
