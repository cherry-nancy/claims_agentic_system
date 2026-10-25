"""Invariants of the Step 1 sample (data/sample/). Prints nothing from the notes."""
import json

import duckdb
import pytest

from snf_pa.data import config as C

SAMPLE = C.SAMPLE_DIR / "sample_cases.parquet"
NOTES = C.SAMPLE_DIR / "notes_raw.parquet"
N = 300

pytestmark = pytest.mark.skipif(not SAMPLE.exists(), reason="run snf_pa.data.build_sample first")


def q(sql: str):
    return duckdb.sql(sql.format(s=C.sql_path(SAMPLE), n=C.sql_path(NOTES))).fetchall()


def test_size_and_balance():
    assert q("select count(*) from '{s}'")[0][0] == N
    for cat in C.CATEGORIES:
        assert q(f"select count(*) from '{{s}}' where category = '{cat}'")[0][0] == 60
        assert q(f"select count(*) from '{{s}}' where category = '{cat}' and label_snf = 1")[0][0] == 30
    n_test = q("select count(*) from '{s}' where split = 'test'")[0][0]
    assert 0.38 * N <= n_test <= 0.46 * N


def test_batch1_is_the_original_50_cases():
    assert q("select count(*) from '{s}' where batch = 1")[0][0] == 50
    for cat in C.CATEGORIES:
        assert q(f"select count(*) from '{{s}}' where batch = 1 and category = '{cat}'")[0][0] == 10


def test_one_admission_per_patient_so_no_split_leakage():
    assert q("select count(distinct subject_id) from '{s}'")[0][0] == N
    assert q("select count(distinct hadm_id) from '{s}'")[0][0] == N


def test_inclusion_criteria():
    assert q(f"select count(*) from '{{s}}' where age_at_admit < {C.MIN_AGE}")[0][0] == 0
    assert q(f"select count(*) from '{{s}}' where inpatient_midnights < {C.MIN_MIDNIGHTS}")[0][0] == 0
    assert q("select count(*) from '{s}' where admission_type ilike '%OBSERVATION%'")[0][0] == 0
    assert q("select count(*) from '{s}' where label_snf != (discharge_location = 'SKILLED NURSING FACILITY')::INT")[0][0] == 0
    assert q("select count(*) from '{s}' where discharge_location not in ('SKILLED NURSING FACILITY','HOME HEALTH CARE','HOME')")[0][0] == 0


def test_every_case_has_exactly_one_note():
    assert q("select count(*) from '{n}'")[0][0] == N
    assert q("select count(distinct hadm_id) from '{n}'")[0][0] == N
    assert q("select count(*) from '{s}' s left join '{n}' n using (hadm_id) where n.hadm_id is null")[0][0] == 0
    assert q("select count(*) from '{n}' where text is null or length(text) < 500")[0][0] == 0


def test_manifest_matches():
    m = json.loads((C.SAMPLE_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert m["n_cases"] == N and m["seed"] == C.SEED
