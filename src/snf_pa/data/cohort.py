"""Step 1: build the candidate pool and draw the stratified sample (DuckDB, no pandas)."""
import duckdb

from . import config as C

NOTE_COLUMNS = (
    "{'note_id':'VARCHAR','subject_id':'BIGINT','hadm_id':'BIGINT','note_type':'VARCHAR',"
    "'note_seq':'INT','charttime':'VARCHAR','storetime':'VARCHAR','text':'VARCHAR'}"
)

# Diagnosis category from the PRIMARY diagnosis (seq_num = 1), ICD-9 and ICD-10.
# Joint replacement is identified by procedure instead (see joint_proc).
CATEGORY_CASE = """
case
  when (d.icd_version = 10 and (d.icd_code like 'S720%' or d.icd_code like 'S721%' or d.icd_code like 'S722%'))
    or (d.icd_version = 9 and d.icd_code like '820%') then 'hip_fracture'
  when (d.icd_version = 10 and d.icd_code like 'I63%')
    or (d.icd_version = 9 and d.icd_code like '434%') then 'stroke'
  when (d.icd_version = 10 and d.icd_code like 'I50%')
    or (d.icd_version = 9 and d.icd_code like '428%') then 'heart_failure'
  when (d.icd_version = 10 and (d.icd_code like 'J18%' or d.icd_code like 'J15%' or d.icd_code like 'A41%'))
    or (d.icd_version = 9 and (d.icd_code like '486%' or d.icd_code like '038%')) then 'pneumonia_sepsis'
  when j.hadm_id is not null then 'joint_replacement'
end
"""


def connect() -> duckdb.DuckDBPyConnection:
    return duckdb.connect()


def build_candidates(con: duckdb.DuckDBPyConnection) -> None:
    """Create table `cand`: every Medicare admission that could enter the study, with flags."""
    h = C.sql_path(C.HOSP)
    con.execute(f"""
        create or replace table note_ids as
        select distinct hadm_id from read_csv('{C.sql_path(C.NOTE_FILE)}', header=true, quote='"',
            escape='"', columns={NOTE_COLUMNS})
    """)
    locs = ", ".join(f"'{k}'" for k in C.LOCATION_QUOTAS)
    con.execute(f"""
        create or replace table cand as
        with joint_proc as (
            select distinct hadm_id from read_csv_auto('{h}/procedures_icd.csv.gz', types={{'icd_code':'VARCHAR'}})
            where (icd_version = 10 and (icd_code like '0SR9%' or icd_code like '0SRB%'
                                         or icd_code like '0SRC%' or icd_code like '0SRD%'))
               or (icd_version = 9 and icd_code in ('8151','8152','8154','8155'))
        ), obs_unit as (
            select distinct hadm_id from read_csv_auto('{h}/transfers.csv.gz') where careunit = 'Observation'
        ), icu as (
            select distinct hadm_id from read_csv_auto('{C.sql_path(C.ICU)}/icustays.csv.gz')
        ), base as (
            select a.subject_id, a.hadm_id, a.admittime, a.dischtime, a.admission_type, a.admission_location,
                   a.discharge_location, a.race, a.language, a.marital_status, p.gender,
                   p.anchor_age + (year(a.admittime) - p.anchor_year) as age_at_admit,
                   date_diff('day', a.admittime::date, a.dischtime::date) as inpatient_midnights
            from read_csv_auto('{h}/admissions.csv.gz') a
            join read_csv_auto('{h}/patients.csv.gz') p using (subject_id)
            where a.insurance = 'Medicare' and a.hospital_expire_flag = 0
              and a.admission_type not ilike '%OBSERVATION%'
              and a.discharge_location in ({locs})
        )
        select b.*, d.icd_code as primary_icd_code, d.icd_version as primary_icd_version,
               {CATEGORY_CASE} as category,
               (o.hadm_id is not null) as had_observation_unit,
               (i.hadm_id is not null) as had_icu,
               (n.hadm_id is not null) as has_note
        from base b
        left join read_csv_auto('{h}/diagnoses_icd.csv.gz', types={{'icd_code':'VARCHAR'}}) d
               on d.hadm_id = b.hadm_id and d.seq_num = 1
        left join joint_proc j on j.hadm_id = b.hadm_id
        left join obs_unit o on o.hadm_id = b.hadm_id
        left join icu i on i.hadm_id = b.hadm_id
        left join note_ids n on n.hadm_id = b.hadm_id
        where b.age_at_admit >= {C.MIN_AGE} and b.inpatient_midnights >= {C.MIN_MIDNIGHTS}
    """)


def eligible_filter() -> str:
    return "category is not null and has_note and not had_observation_unit"


def candidate_counts(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    return con.execute(f"""
        select category, discharge_location, count(*) as n_eligible, count(distinct subject_id) as n_patients
        from cand where {eligible_filter()}
        group by 1, 2 order by 1, 2
    """).fetchall()


def effective_quotas(pool: dict[tuple[str, str], int]) -> dict[tuple[str, str], int]:
    """Target quotas capped by the eligible pool; shortfalls move along C.NEGATIVE_FALLBACK."""
    out: dict[tuple[str, str], int] = {}
    for cat in C.CATEGORIES:
        want = dict(C.LOCATION_QUOTAS)
        for loc in want:
            have = pool.get((cat, loc), 0)
            if want[loc] > have:
                short = want[loc] - have
                want[loc] = have
                fb = C.NEGATIVE_FALLBACK.get(loc)
                if fb:
                    want[fb] += short
        for loc, n in want.items():
            out[(cat, loc)] = min(n, pool.get((cat, loc), 0))
    return out


def draw_sample(con: duckdb.DuckDBPyConnection) -> dict[tuple[str, str], int]:
    """Create table `sample`: one admission per patient, quota per (category, discharge_location)."""
    con.execute(f"""
        create or replace table ranked as
        with one_per_patient as (
            select * from (
                select *, row_number() over (partition by subject_id order by hash(hadm_id + {C.SEED})) as srn
                from cand where {eligible_filter()}
            ) where srn = 1
        )
        select *, row_number() over (partition by category, discharge_location
                                     order by hash(hadm_id + {C.SEED})) as rn
        from one_per_patient
    """)
    pool = {
        (c, loc): n
        for c, loc, n in con.execute("select category, discharge_location, count(*) from ranked group by 1, 2").fetchall()
    }
    quotas = effective_quotas(pool)
    values = ", ".join(f"('{c}', '{loc}', {n})" for (c, loc), n in quotas.items())
    b1 = ", ".join(f"('{loc}', {n})" for loc, n in C.BATCH1_QUOTAS.items())
    test_pos = ", ".join(str(p) for p in C.TEST_POSITIONS)
    con.execute(f"""
        create or replace table sample as
        with quotas(category, discharge_location, n_total) as (values {values}),
             b1(discharge_location, n_b1) as (values {b1})
        select r.subject_id, r.hadm_id, r.category,
               (r.discharge_location = 'SKILLED NURSING FACILITY')::INT as label_snf,
               r.discharge_location,
               case when r.rn % {C.TEST_MODULUS} in ({test_pos}) then 'test' else 'dev' end as split,
               case when r.rn <= b1.n_b1 then 1 else 2 end as batch,
               r.admission_type, r.admission_location, r.age_at_admit, r.gender, r.race, r.language,
               r.marital_status, r.inpatient_midnights, r.had_icu,
               r.primary_icd_code, r.primary_icd_version, t.long_title as primary_dx_title,
               r.admittime, r.dischtime
        from ranked r join quotas q using (category, discharge_location)
        join b1 using (discharge_location)
        left join read_csv_auto('{C.sql_path(C.HOSP)}/d_icd_diagnoses.csv.gz', types={{'icd_code':'VARCHAR'}}) t
               on t.icd_code = r.primary_icd_code and t.icd_version = r.primary_icd_version
        where r.rn <= q.n_total
        order by r.category, r.discharge_location, r.hadm_id
    """)
    return quotas


def export_notes(con: duckdb.DuckDBPyConnection, out_path) -> int:
    """Copy the raw discharge summaries of the sampled admissions to a local parquet file."""
    con.execute(f"""
        copy (
            select note_id, hadm_id, text
            from read_csv('{C.sql_path(C.NOTE_FILE)}', header=true, quote='"', escape='"',
                          columns={NOTE_COLUMNS})
            where hadm_id in (select hadm_id from sample)
        ) to '{C.sql_path(out_path)}' (format parquet)
    """)
    return con.execute(f"select count(*) from read_parquet('{C.sql_path(out_path)}')").fetchall()[0][0]
