"""data/splits/admissions.csv: one row per pool admission, deterministic rule (design v9: split by hadm_id)."""
import csv
import importlib.util
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[1]
SPLIT = ROOT / "data" / "splits" / "admissions.csv"
POOL = ROOT / "data" / "derived" / "cohort" / "pool.parquet"

pytestmark = pytest.mark.skipif(not SPLIT.exists(), reason="split not generated yet")

_spec = importlib.util.spec_from_file_location("make_split", ROOT / "research" / "make_split.py")
make_split = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(make_split)


@pytest.fixture(scope="module")
def rows():
    with SPLIT.open(encoding="utf-8") as f:
        return [(int(r["hadm_id"]), int(r["subject_id"]), r["split"]) for r in csv.DictReader(f)]


def test_each_admission_once_and_only_dev_or_test(rows):
    ids = [h for h, _, _ in rows]
    assert len(ids) == len(set(ids))
    assert {sp for _, _, sp in rows} == {"dev", "test"}


def test_rule_reproduces_file(rows):
    assert all(make_split.assign(h) == sp for h, _, sp in rows)


def test_ratio_close_to_setting(rows):
    dev = sum(sp == "dev" for _, _, sp in rows) / len(rows)
    assert abs(dev - make_split.DEV_FRACTION) < 0.02


@pytest.mark.skipif(not POOL.exists(), reason="pool.parquet not built on this machine")
def test_covers_exactly_the_pool_admissions(rows):
    pool = set(duckdb.sql(f"select hadm_id, subject_id from '{POOL.as_posix()}'").fetchall())
    assert {(h, s) for h, s, _ in rows} == pool
