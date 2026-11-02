"""SQL for the candidate pool, the per-stratum draw and the note export."""
import duckdb

from snf_pa.data import config as C

LOCATIONS = list(C.QUOTAS[1])

# First listed diagnosis (seq_num = 1) decides the category; ICD codes in MIMIC carry no dots.
DX_CATEGORY = """
case
  when (icd_version = 10 and (icd_code like 'S720%' or icd_code like 'S721%' or icd_code like 'S722%'))
    or (icd_version = 9 and icd_code like '820%') then 'hip_fracture'
  when (icd_version = 10 and (icd_code like 'I61%' or icd_code like 'I63%'))
    or (icd_version = 9 and (icd_code like '431%' or icd_code like '433_1' or icd_code like '434_1'
                             or icd_code like '436%')) then 'stroke'
  when (icd_version = 10 and (icd_code like 'I50%' or icd_code in ('I110', 'I130', 'I132')))
    or (icd_version = 9 and (icd_code like '428%' or icd_code in ('40201', '40211', '40291', '40401',
                             '40403', '40411', '40413', '40491', '40493'))) then 'heart_failure'
  when (icd_version = 10 and (regexp_matches(icd_code, '^J1[2-8]') or icd_code like 'A40%' or icd_code like 'A41%'))
    or (icd_version = 9 and (regexp_matches(icd_code, '^48[0-6]') or icd_code like '038%'
                             or icd_code in ('99591', '99592'))) then 'pneumonia_sepsis'
end
"""

# Hip and knee replacement: ICD-10-PCS 0SR9/0SRB (hip), 0SRC/0SRD (knee); ICD-9 81.51, 81.52, 81.54.
JOINT_PROC = """
(icd_version = 10 and (icd_code like '0SR9%' or icd_code like '0SRB%' or icd_code like '0SRC%'
                       or icd_code like '0SRD%'))
or (icd_version = 9 and icd_code in ('8151', '8152', '8154'))
"""


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("set memory_limit = '4GB'")
    return con


def build_candidates(con: duckdb.DuckDBPyConnection) -> None:
    """Table `candidates`: every eligible admission, one per patient, with its category."""
    h, i, n = C.sql_path(C.HOSP), C.sql_path(C.ICU), C.sql_path(C.NOTE)
    locs = ", ".join(f"'{loc}'" for loc in LOCATIONS)
    con.execute(f"""
    create or replace table notes_index as
    select note_id, hadm_id, note_seq, length(text) as n_chars
    from read_csv('{n}/discharge.csv.gz', header = true, quote = '"', escape = '"')
    where hadm_id is not null
    qualify row_number() over (partition by hadm_id order by note_seq desc, charttime desc) = 1
    """)
    con.execute(f"""
    create or replace table candidates as
    with adm as (
      select a.*, p.gender,
             p.anchor_age + (year(a.admittime) - p.anchor_year) as age_at_admit,
             date_diff('day', a.admittime::date, a.dischtime::date) as inpatient_midnights,
             round(epoch(a.dischtime - a.admittime) / 86400.0, 2) as los_days
      from read_csv_auto('{h}/admissions.csv.gz') a
      join read_csv_auto('{h}/patients.csv.gz') p using (subject_id)
    ),
    dx1 as (
      select d.hadm_id, d.icd_code as first_dx_code, d.icd_version as first_dx_version,
             t.long_title as first_dx_title, {DX_CATEGORY} as dx_category
      from read_csv_auto('{h}/diagnoses_icd.csv.gz', types = {{'icd_code': 'VARCHAR'}}) d
      left join read_csv_auto('{h}/d_icd_diagnoses.csv.gz', types = {{'icd_code': 'VARCHAR'}}) t
        using (icd_code, icd_version)
      where d.seq_num = 1
    ),
    joint as (
      select distinct hadm_id
      from read_csv_auto('{h}/procedures_icd.csv.gz', types = {{'icd_code': 'VARCHAR'}})
      where {JOINT_PROC}
    ),
    obs_unit as (
      select distinct hadm_id from read_csv_auto('{h}/transfers.csv.gz') where careunit = 'Observation'
    ),
    icu as (select distinct hadm_id from read_csv_auto('{i}/icustays.csv.gz')),
    eligible as (
      select adm.*, dx1.first_dx_code, dx1.first_dx_version, dx1.first_dx_title,
             case when dx1.dx_category = 'hip_fracture' then 'hip_fracture'
                  when joint.hadm_id is not null then 'joint_replacement'
                  else dx1.dx_category end as category,
             (icu.hadm_id is not null) as icu_any,
             (adm.discharge_location = 'SKILLED NURSING FACILITY')::INT as label_snf,
             ni.note_id
      from adm
      join dx1 using (hadm_id)
      join notes_index ni on ni.hadm_id = adm.hadm_id and ni.n_chars >= 500
      left join joint on joint.hadm_id = adm.hadm_id
      left join icu on icu.hadm_id = adm.hadm_id
      where adm.insurance = 'Medicare'
        and adm.age_at_admit >= {C.MIN_AGE}
        and adm.hospital_expire_flag = 0
        and adm.inpatient_midnights >= {C.MIN_MIDNIGHTS}
        and adm.admission_type not ilike '%OBSERVATION%'
        and adm.hadm_id not in (select hadm_id from obs_unit)
        and adm.discharge_location in ({locs})
    )
    select * from eligible
    where category is not null
    -- one admission per patient (seeded), so a patient can never sit in both dev and test
    qualify row_number() over (partition by subject_id order by md5(hadm_id::VARCHAR || ':{C.SEED}')) = 1
    """)


def candidate_counts(con: duckdb.DuckDBPyConnection):
    return con.sql("""
    select category, discharge_location, count(*) as n_candidates
    from candidates group by all order by all
    """).pl()


def draw(con: duckdb.DuckDBPyConnection, category: str, location: str, k: int):
    """First k candidates of a stratum in seeded hash order; a smaller k always gives a prefix."""
    return con.sql(f"""
    select *, row_number() over (order by md5(hadm_id::VARCHAR || ':{C.SEED}')) as stratum_rank
    from candidates where category = ? and discharge_location = ?
    order by stratum_rank limit {int(k)}
    """, params=[category, location]).pl()


def export_notes(con: duckdb.DuckDBPyConnection, note_ids: list[str], out_path) -> None:
    n = C.sql_path(C.NOTE)
    con.execute("create or replace temp table wanted as select unnest(?::VARCHAR[]) as note_id", [note_ids])
    con.execute(f"""
    copy (
      select d.note_id, d.subject_id, d.hadm_id, d.charttime, d.text
      from read_csv('{n}/discharge.csv.gz', header = true, quote = '"', escape = '"') d
      join wanted using (note_id)
      order by d.hadm_id
    ) to '{C.sql_path(out_path)}' (format parquet)
    """)
