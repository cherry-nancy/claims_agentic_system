"""Timeline / T_pa on synthetic orders, plus the Appendix A POE counts on raw data (slow)."""
import json
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import pytest

from snf_pa.adapters import timeline as tl

D = datetime.fromisoformat


@pytest.fixture()
def con():
    c = duckdb.connect()
    c.execute("create table admissions (subject_id BIGINT, hadm_id BIGINT, admittime TIMESTAMP, dischtime TIMESTAMP)")
    c.executemany("insert into admissions values (?,?,?,?)", [
        (1, 11, D("2150-01-01 10:00"), D("2150-01-06 12:00")),   # inpatient order day 1
        (2, 21, D("2150-01-01 10:00"), D("2150-01-05 12:00")),   # observation, then converted (Change) day 3
        (3, 31, D("2150-01-01 10:00"), D("2150-01-04 12:00")),   # no inpatient order -> fallback
        (4, 41, D("2150-01-01 10:00"), D("2150-01-04 12:00")),   # only a Discharge order carries the category
        (5, 51, D("2150-01-01 10:00"), D("2150-01-01 20:00")),   # 10 h stay: T_pa = inpatient start
        (1, 10, D("2149-12-10 08:00"), D("2149-12-20 08:00")),   # prior stay, discharged 17 days before current discharge
        (1, 8, D("2149-12-01 08:00"), D("2149-12-05 08:00")),    # 27 days before admission but 32 before discharge
        (1, 9, D("2149-10-01 08:00"), D("2149-10-05 08:00")),    # older than 30 days
    ])
    c.execute("create table poe (poe_id VARCHAR, hadm_id BIGINT, ordertime TIMESTAMP, order_type VARCHAR, order_subtype VARCHAR, transaction_type VARCHAR)")
    c.execute("create table poe_detail (poe_id VARCHAR, field_name VARCHAR, field_value VARCHAR)")
    rows = [("a", 11, D("2150-01-01 09:00"), "Admit", "New", "Admit to inpatient"),        # placed in ED before admittime
            ("b", 21, D("2150-01-01 09:00"), "Admit", "New", "Place in observation"),
            ("c", 21, D("2150-01-03 15:00"), "Admit", "Change", "Admit to inpatient"),
            ("d", 41, D("2150-01-04 11:00"), "Discharge", "New", "Admit to inpatient"),
            ("e", 51, D("2150-01-01 10:30"), "Admit", "New", "Admit to inpatient")]
    for pid, h, t, sub, tt, cat in rows:
        c.execute("insert into poe values (?,?,?,?,?,?)", [pid, h, t, "ADT orders", sub, tt])
        c.execute("insert into poe_detail values (?,?,?)", [pid, "Admit category", cat])
    c.execute("create table edstays (hadm_id BIGINT, intime TIMESTAMP, outtime TIMESTAMP)")
    c.execute("insert into edstays values (11, '2150-01-01 06:00', '2150-01-01 11:00')")
    tl.build_timeline(c)
    tl.prior_stays(c)
    return c


def row(c, h):
    cols = [d[0] for d in c.execute("select * from timeline limit 0").description]
    return dict(zip(cols, c.execute("select * from timeline where hadm_id = ?", [h]).fetchone()))


def test_inpatient_order_before_admittime_counts(con):
    r = row(con, 11)
    assert r["inpatient_start"] == D("2150-01-01 09:00") and r["inpatient_start_source"] == "poe_admit_inpatient"
    assert r["midnights"] == 5 and r["ed_intime"] == D("2150-01-01 06:00")
    assert r["t_pa"] == D("2150-01-05 12:00")


def test_observation_then_change_to_inpatient(con):
    r = row(con, 21)
    assert r["observation_order_time"] == D("2150-01-01 09:00")
    assert r["inpatient_start"] == D("2150-01-03 15:00") and r["midnights"] == 2


def test_no_order_falls_back_and_flags(con):
    r = row(con, 31)
    assert r["inpatient_start_source"] == "admittime_fallback" and r["inpatient_start"] == D("2150-01-01 10:00")


def test_discharge_order_never_used_as_start(con):
    r = row(con, 41)
    assert r["inpatient_order_time"] is None and r["inpatient_start_source"] == "admittime_fallback"


def test_short_stay_t_pa_is_inpatient_start(con):
    r = row(con, 51)
    assert r["t_pa"] == D("2150-01-01 10:30")


def test_prior_stays_within_30_days_of_current_discharge(con):
    """42 CFR 409.30(b)(1): 30 days counted from the qualifying stay's discharge to the SNF admission
    (= current discharge). Stay 8 is 27 days before the current admission but 32 before its discharge."""
    got = con.execute("select prior_hadm_id from prior_stays where hadm_id = 11").fetchall()
    assert got == [(10,)]


EXPECTED = json.loads((Path(__file__).parent / "expected" / "appendix_a_poe.json").read_text(encoding="utf-8"))


@pytest.mark.slow
def test_appendix_a_poe_counts_on_raw():
    from snf_pa.adapters import cohort
    from snf_pa.paths import raw_table, sql_path

    c = cohort.connect()
    cohort.load_medicare(c)
    c.execute(f"create temp table snf as select * from medicare where discharge_location = '{cohort.SNF}'")
    c.execute("create view admissions as select * from snf")
    for name, tbl in [("poe", "mimiciv-3.1/hosp/poe"), ("poe_detail", "mimiciv-3.1/hosp/poe_detail"),
                      ("edstays", "mimic-iv-ed/ed/edstays")]:
        c.execute(f"create view {name} as select * from read_csv('{sql_path(raw_table(tbl))}', header=true)")
    tl.build_timeline(c, "snf", subtypes=tl.APPENDIX_A_SUBTYPES)
    pct, obs2inp, ge3 = c.execute("""
        select 100 * avg((t.inpatient_order_time is not null)::int) filter (where s.has_note),
               count(*) filter (where t.observation_order_time <= t.inpatient_order_time),
               count(*) filter (where t.midnights >= 3)
        from timeline t join snf s using (hadm_id)""").fetchone()
    assert round(pct) == EXPECTED["snf_note_pct_with_inpatient_order_rounded"]
    assert obs2inp == EXPECTED["snf_observation_then_inpatient"]
    assert ge3 == EXPECTED["snf_midnights_ge3_by_inpatient_order"]
