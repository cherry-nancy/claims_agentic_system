"""Study cohort (design §3.2) built from the raw MIMIC tables with DuckDB. Read-only on MIMIC_RAW_DIR.

Candidate pool = Medicare, age >= 65 at admission, discharged alive, has a discharge summary, admission
year certainly within 2011-2018, discharge location in {SNF, HHC, HOME} (REHAB excluded, decision_log D-008).

Not filters (they are stratification variables, design §3.2 / §10.1): observation status, inpatient
midnights, admission from a SNF. C1 itself is computed later by the rule engine from POE orders (§6.2).

Year rule ("strict", user decision 2026-11-08): MIMIC dates are shifted; the real year of anchor_year lies
in anchor_year_group (3 years). With offset = year(admittime) - anchor_year, the real admission year lies in
[group_start + offset, group_end + offset]. An admission is kept only if that whole interval is inside
2011-2018.

Field definitions match design Appendix A (tests/test_cohort_counts.py checks the counts).
"""
from __future__ import annotations

import duckdb

from snf_pa.paths import raw_table, sql_path

SNF = "SKILLED NURSING FACILITY"
HHC = "HOME HEALTH CARE"
HOME = "HOME"
DISPOSITIONS = (SNF, HHC, HOME)   # REHAB (IRF) excluded by team decision 2026-11-09 (decision_log D-008)
FROM_SNF = "TRANSFER FROM SKILLED NURSING FACILITY"
MIN_AGE = 65
YEAR_FIRST, YEAR_LAST = 2011, 2018

NOTE_COLUMNS = (
    "{'note_id':'VARCHAR','subject_id':'BIGINT','hadm_id':'BIGINT','note_type':'VARCHAR',"
    "'note_seq':'INT','charttime':'VARCHAR','storetime':'VARCHAR','text':'VARCHAR'}"
)


def connect() -> duckdb.DuckDBPyConnection:
    return duckdb.connect()


def load_medicare(con: duckdb.DuckDBPyConnection) -> None:
    """Temp table `medicare`: every Medicare admission with the derived fields used by the cohort."""
    adm = sql_path(raw_table("mimiciv-3.1/hosp/admissions"))
    pat = sql_path(raw_table("mimiciv-3.1/hosp/patients"))
    dis = sql_path(raw_table("mimic-iv-note/note/discharge"))
    con.execute(f"""
        create or replace temp table note_hadm as
        select distinct hadm_id from read_csv('{dis}', header=true, columns={NOTE_COLUMNS})
        where hadm_id is not null
    """)
    con.execute(f"""
        create or replace temp table medicare as
        select a.subject_id, a.hadm_id, a.admittime, a.dischtime, a.admission_type, a.admission_location,
               a.discharge_location, a.insurance, a.language, a.marital_status, a.race,
               a.hospital_expire_flag, p.gender, p.anchor_age, p.anchor_year, p.anchor_year_group,
               p.anchor_age + (year(a.admittime) - p.anchor_year) as age_at_admit,
               cast(substr(p.anchor_year_group, 1, 4) as int) + (year(a.admittime) - p.anchor_year)
                   as real_year_min,
               cast(substr(p.anchor_year_group, 8, 4) as int) + (year(a.admittime) - p.anchor_year)
                   as real_year_max,
               date_diff('day', a.admittime::date, a.dischtime::date) as naive_midnights,
               a.admission_type ilike '%OBSERVATION%' as observation_admit_type,
               a.admission_location = '{FROM_SNF}' as from_snf,
               n.hadm_id is not null as has_note
        from read_csv_auto('{adm}') a
        join read_csv_auto('{pat}') p using (subject_id)
        left join note_hadm n using (hadm_id)
        where a.insurance = 'Medicare'
    """)


POOL_WHERE = f"""
    age_at_admit >= {MIN_AGE}
    and hospital_expire_flag = 0
    and has_note
    and real_year_min >= {YEAR_FIRST} and real_year_max <= {YEAR_LAST}
    and discharge_location in ({", ".join(f"'{d}'" for d in DISPOSITIONS)})
"""


def build_pool(con: duckdb.DuckDBPyConnection) -> None:
    """Temp table `pool`: the candidate pool, one row per admission, with the primary diagnosis."""
    dx = sql_path(raw_table("mimiciv-3.1/hosp/diagnoses_icd"))
    con.execute(f"""
        create or replace temp table pool as
        select m.*, d.icd_code as primary_icd_code, d.icd_version as primary_icd_version
        from medicare m
        left join (select hadm_id, icd_code, icd_version
                   from read_csv_auto('{dx}', types={{'icd_code':'VARCHAR'}}) where seq_num = 1) d
               using (hadm_id)
        where {POOL_WHERE}
        order by hadm_id
    """)


def pool_counts(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    return con.execute("""
        select discharge_location, count(*) as admissions, count(distinct subject_id) as patients,
               sum(observation_admit_type::int) as observation_type, sum((naive_midnights < 3)::int) as lt3_naive,
               sum(from_snf::int) as from_snf
        from pool group by 1 order by 2 desc
    """).fetchall()


def main() -> None:
    """Write data/derived/cohort/pool.parquet and print per-disposition counts."""
    import json
    from snf_pa.paths import ROOT

    out = ROOT / "data" / "derived" / "cohort"
    out.mkdir(parents=True, exist_ok=True)
    con = connect()
    load_medicare(con)
    build_pool(con)
    con.execute(f"copy pool to '{sql_path(out / 'pool.parquet')}' (format parquet)")
    rows = pool_counts(con)
    cols = ["discharge_location", "admissions", "patients", "observation_type", "lt3_naive", "from_snf"]
    summary = {"year_rule": f"strict {YEAR_FIRST}-{YEAR_LAST}", "by_disposition": [dict(zip(cols, r)) for r in rows],
               "total_admissions": con.execute("select count(*) from pool").fetchone()[0],
               "total_patients": con.execute("select count(distinct subject_id) from pool").fetchone()[0]}
    (out / "pool_counts.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
