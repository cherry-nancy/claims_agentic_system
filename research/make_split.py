"""Split the candidate pool's admissions into dev / test by hadm_id (design v9 §3.2, §10.1; CLAUDE.md rule 3).

    uv run python -m snf_pa.adapters.cohort      # builds data/derived/cohort/pool.parquet
    uv run python research/make_split.py         # writes data/splits/admissions.csv (+ .meta.json)

Rule: u = first 8 hex digits of sha256(f"{SALT}:{hadm_id}") / 16**8; dev if u < DEV_FRACTION else test.
Deterministic on any machine. Team decision 2026-11-09 (decision_log D-008): the unit is the admission, so two
admissions of one patient may fall in different splits (known limitation, design §3.2).
Supersedes the patient-level data/splits/subjects.csv (salt snf-pa-split-v1), kept in git history.

Refuses to overwrite an existing split: once frozen (tools/freeze.py) it must not change.
"""
from __future__ import annotations

import hashlib
import json
import sys

import duckdb

from snf_pa.paths import ROOT

SALT = "snf-pa-split-v2"
DEV_FRACTION = 0.5  # user decision 2026-11-08
POOL = ROOT / "data" / "derived" / "cohort" / "pool.parquet"
OUT = ROOT / "data" / "splits" / "admissions.csv"
META = ROOT / "data" / "splits" / "admissions.meta.json"


def assign(hadm_id: int) -> str:
    u = int(hashlib.sha256(f"{SALT}:{hadm_id}".encode()).hexdigest()[:8], 16) / 16**8
    return "dev" if u < DEV_FRACTION else "test"


def main() -> None:
    if OUT.exists() or META.exists():
        sys.exit(f"{OUT} already exists; the split is protected and is never regenerated.")
    if not POOL.exists():
        sys.exit(f"{POOL} missing; run `uv run python -m snf_pa.adapters.cohort` first.")
    rows = duckdb.sql(f"select hadm_id, subject_id from '{POOL.as_posix()}' order by hadm_id").fetchall()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="\n") as f:
        f.write("hadm_id,subject_id,split\n")
        for h, s in rows:
            f.write(f"{h},{s},{assign(h)}\n")
    n_dev = sum(assign(h) == "dev" for h, _ in rows)
    split_of: dict[int, set] = {}
    for h, s in rows:
        split_of.setdefault(s, set()).add(assign(h))
    META.write_text(json.dumps({
        "rule": "sha256(f'{salt}:{hadm_id}')[:8] / 16**8 < dev_fraction -> dev, else test",
        "salt": SALT, "dev_fraction": DEV_FRACTION, "unit": "admission (hadm_id)",
        "source": "data/derived/cohort/pool.parquet (strict year rule 2011-2018, SNF/HHC/HOME, design v9 §3.2)",
        "n_admissions": len(rows), "n_dev": n_dev, "n_test": len(rows) - n_dev,
        "n_patients": len(split_of), "n_patients_in_both_splits": sum(len(v) == 2 for v in split_of.values()),
    }, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {OUT}: {len(rows)} admissions, dev {n_dev}, test {len(rows) - n_dev}; "
          f"patients in both splits {sum(len(v) == 2 for v in split_of.values())}")


if __name__ == "__main__":
    main()
