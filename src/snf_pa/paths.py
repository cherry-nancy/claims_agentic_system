"""Where the raw MIMIC files live. Read-only access (CLAUDE.md hard rule 1).

The root comes from MIMIC_RAW_DIR (.env or the environment); there is no default, a missing root is an
error. Layout under the root: mimiciv-3.1/{hosp,icu}, mimic-iv-ed/ed, mimic-iv-note/note.
Each table may be stored uncompressed (.csv) or as shipped by PhysioNet (.csv.gz); .csv wins when both
exist. DuckDB reads either form with read_csv.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
ENV_VAR = "MIMIC_RAW_DIR"


def raw_dir() -> Path:
    load_dotenv(ROOT / ".env", override=False)
    val = os.environ.get(ENV_VAR, "").strip()
    if not val:
        raise RuntimeError(f"{ENV_VAR} is not set; copy .env.example to .env and set it")
    p = Path(val)
    if not p.is_dir():
        raise FileNotFoundError(f"{ENV_VAR}={val} is not a directory")
    return p


def raw_table(name: str) -> Path:
    """Path of a raw table, e.g. raw_table("mimiciv-3.1/hosp/admissions") -> .../admissions.csv(.gz)."""
    base = raw_dir() / name
    for suffix in (".csv", ".csv.gz"):
        f = base.with_name(base.name + suffix)
        if f.is_file():
            return f
    raise FileNotFoundError(f"raw table not found: {base}.csv or {base}.csv.gz")


def sql_path(p: Path) -> str:
    """Forward-slash path for DuckDB SQL strings."""
    return p.as_posix()
