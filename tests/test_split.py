"""data/splits/subjects.csv: one row per patient, deterministic rule, matches the candidate pool."""
import csv
import importlib.util
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[1]
SPLIT = ROOT / "data" / "splits" / "subjects.csv"
POOL = ROOT / "data" / "derived" / "cohort" / "pool.parquet"

pytestmark = pytest.mark.skipif(not SPLIT.exists(), reason="split not generated yet")

_spec = importlib.util.spec_from_file_location("make_split", ROOT / "research" / "make_split.py")
make_split = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(make_split)


@pytest.fixture(scope="module")
def rows():
    with SPLIT.open(encoding="utf-8") as f:
        return [(int(r["subject_id"]), r["split"]) for r in csv.DictReader(f)]


def test_each_patient_once_and_only_dev_or_test(rows):
    ids = [s for s, _ in rows]
    assert len(ids) == len(set(ids))
    assert {sp for _, sp in rows} == {"dev", "test"}


def test_rule_reproduces_file(rows):
    assert all(make_split.assign(s) == sp for s, sp in rows)


def test_ratio_close_to_setting(rows):
    dev = sum(sp == "dev" for _, sp in rows) / len(rows)
    assert abs(dev - make_split.DEV_FRACTION) < 0.02


@pytest.mark.skipif(not POOL.exists(), reason="pool.parquet not built on this machine")
def test_covers_exactly_the_pool_patients(rows):
    pool = {r[0] for r in duckdb.sql(f"select distinct subject_id from '{POOL.as_posix()}'").fetchall()}
    assert {s for s, _ in rows} == pool
