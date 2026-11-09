"""Cohort SQL vs design Appendix A counts, and candidate-pool invariants. Reads raw MIMIC (slow)."""
import json
from pathlib import Path

import pytest

from snf_pa.adapters import cohort

pytestmark = pytest.mark.slow

EXPECTED = json.loads((Path(__file__).parent / "expected" / "appendix_a.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def con():
    c = cohort.connect()
    cohort.load_medicare(c)
    cohort.build_pool(c)
    return c


def one(con, sql):
    return con.execute(sql).fetchone()[0]


SNF = f"discharge_location = '{cohort.SNF}'"


def test_appendix_a_counts(con):
    got = {
        "medicare_admissions": one(con, "select count(*) from medicare"),
        "medicare_snf": one(con, f"select count(*) from medicare where {SNF}"),
        "snf_with_note": one(con, f"select count(*) from medicare where {SNF} and has_note"),
        "snf_note_age65_alive": one(con, f"""select count(*) from medicare where {SNF} and has_note
                                             and age_at_admit >= 65 and hospital_expire_flag = 0"""),
        "snf_observation_admit": one(con, f"""select count(*) from medicare where {SNF}
                                              and admission_type ilike '%OBSERVATION ADMIT%'"""),
        "snf_naive_midnights_ge3": one(con, f"select count(*) from medicare where {SNF} and naive_midnights >= 3"),
        "snf_naive_midnights_lt3": one(con, f"select count(*) from medicare where {SNF} and naive_midnights < 3"),
        "snf_from_snf": one(con, f"select count(*) from medicare where {SNF} and from_snf"),
    }
    expected = {k: v for k, v in EXPECTED.items() if not k.startswith("_")}
    assert got == expected


POOL_EXPECTED = json.loads((Path(__file__).parent / "expected" / "pool_counts.json").read_text(encoding="utf-8"))


def test_pool_size_matches_design(con):
    """Pins the year / disposition filters to numbers fixed outside cohort.py (design §3.2, plan probe)."""
    got = {
        "snf_admissions": one(con, f"select count(*) from pool where {SNF}"),
        "snf_patients": one(con, f"select count(distinct subject_id) from pool where {SNF}"),
        "total_admissions": one(con, "select count(*) from pool"),
        "total_patients": one(con, "select count(distinct subject_id) from pool"),
    }
    assert got == {k: v for k, v in POOL_EXPECTED.items() if not k.startswith("_")}


def test_year_window_parsed_independently(con):
    """Recompute the strict year window in Python from the raw fields, not from cohort.py's columns."""
    rows = con.execute("""select anchor_year_group, anchor_year, year(admittime), real_year_min, real_year_max
                          from pool using sample 2000 rows (reservoir, 7)""").fetchall()
    for grp, anchor_year, adm_year, lo, hi in rows:
        start, end = (int(x) for x in grp.replace(" ", "").split("-"))
        offset = adm_year - anchor_year
        assert (lo, hi) == (start + offset, end + offset)
        assert 2011 <= start + offset and end + offset <= 2018


def test_pool_invariants(con):
    assert one(con, "select count(*) from pool") > 0
    assert one(con, f"select count(*) from pool where age_at_admit < {cohort.MIN_AGE}") == 0
    assert one(con, "select count(*) from pool where hospital_expire_flag != 0") == 0
    assert one(con, "select count(*) from pool where not has_note") == 0
    assert one(con, "select count(*) from pool where insurance != 'Medicare'") == 0
    assert one(con, f"""select count(*) from pool where real_year_min < {cohort.YEAR_FIRST}
                        or real_year_max > {cohort.YEAR_LAST}""") == 0
    locs = {r[0] for r in con.execute("select distinct discharge_location from pool").fetchall()}
    assert locs == set(cohort.DISPOSITIONS)
    assert one(con, "select count(*) - count(distinct hadm_id) from pool") == 0
    # stratification variables stay in the pool, they are not filters
    assert one(con, "select count(*) from pool where observation_admit_type") > 0
    assert one(con, "select count(*) from pool where naive_midnights < 3") > 0
    assert one(con, "select count(*) from pool where from_snf") > 0
