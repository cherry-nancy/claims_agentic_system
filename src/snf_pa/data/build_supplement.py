"""Supplement to data/sample/sample_cases1.csv: scenarios the main sample cannot contain.

Run from the project root:
    PYTHONPATH=src uv run python -m snf_pa.data.build_supplement

The main sample (5 diagnosis categories x 60, SNF / HOME HEALTH CARE / HOME, >=3 midnights, no observation
stays) has no C1 boundary cases, no IRF patients, no medical deconditioning and almost no admissions from a
SNF. This draws those scenarios from MIMIC, skipping every patient already in sample_cases1.csv.

Writes data/sample/sample_cases1_supp.{csv,parquet} and notes_raw1_supp.parquet (gitignored).
Prints counts only, never note text or IDs.
"""
import polars as pl

from snf_pa.data import cohort
from snf_pa.data import config as C

MAIN = C.SAMPLE_DIR / "sample_cases1.csv"
OUT = C.SAMPLE_DIR / "sample_cases1_supp"
NOTES_OUT = C.SAMPLE_DIR / "notes_raw1_supp.parquet"
BATCH = 3  # batches 1-2 are sample_cases1.csv

SNF, HHC, HOME, REHAB = "SKILLED NURSING FACILITY", "HOME HEALTH CARE", "HOME", "REHAB"

# Drawn in this order; a patient used by an earlier scenario is not used again.
# Each entry: scenario -> (filter on table `pool`, {discharge_location: n}).
SCENARIOS = {
    "c1_short_prior_stay": ("midnights < 3 and prior_qual_stay", {SNF: 10}),
    "c1_short_no_prior_stay": ("midnights < 3 and not prior_qual_stay", {SNF: 10}),
    "obs_to_inpatient": ("observation and midnights >= 3", {SNF: 20}),
    "admitted_from_snf": ("admission_location = 'TRANSFER FROM SKILLED NURSING FACILITY' "
                          "and not observation and midnights >= 3", {SNF: 10}),
    "irf": ("not observation and midnights >= 3", {REHAB: 40}),
    "deconditioning": ("category is null and pt_consult and not observation and midnights >= 3 "
                       "and admission_type not in ('ELECTIVE', 'SURGICAL SAME DAY ADMISSION')",
                       {SNF: 20, HHC: 12, HOME: 8}),
    "skilled_nursing": ("(skilled_nursing_order or iv_antibiotic_5d) and not observation and midnights >= 3",
                        {SNF: 12, HHC: 8}),
    "dx_gap_hemorrhagic_stroke": ("(icd_code like 'I61%' or icd_code like '431%') "
                                  "and not observation and midnights >= 3", {SNF: 3, HHC: 2}),
    "dx_gap_hypertensive_hf": ("(icd_code in ('I110', 'I130', 'I132') or icd_code in ('40201', '40211', "
                               "'40291', '40401', '40403', '40411', '40413', '40491', '40493')) "
                               "and not observation and midnights >= 3", {SNF: 3, HHC: 2}),
}

# Common IV antibiotics; matched case-insensitively against prescriptions.drug.
IV_ANTIBIOTICS = (
    "vancomycin|cefepime|ceftriaxone|ceftazidime|cefazolin|piperacillin|meropenem|ertapenem|imipenem|"
    "ampicillin|nafcillin|oxacillin|daptomycin|linezolid|levofloxacin|ciprofloxacin|metronidazole|"
    "gentamicin|tobramycin|aztreonam|clindamycin|penicillin|micafungin|fluconazole|acyclovir"
)


def build_pool(con) -> None:
    """Table `pool`: every eligible admission with the flags the scenarios filter on."""
    h, i, n = C.sql_path(C.HOSP), C.sql_path(C.ICU), C.sql_path(C.NOTE)
    con.execute(f"""
    create or replace table notes_index as
    select note_id, hadm_id
    from read_csv('{n}/discharge.csv.gz', header = true, quote = '"', escape = '"')
    where hadm_id is not null and length(text) >= 500
    qualify row_number() over (partition by hadm_id order by note_seq desc, charttime desc) = 1
    """)
    con.execute(f"""
    create or replace table adm as
    select a.*, p.gender,
           p.anchor_age + (year(a.admittime) - p.anchor_year) as age_at_admit,
           date_diff('day', a.admittime::date, a.dischtime::date) as midnights
    from read_csv_auto('{h}/admissions.csv.gz') a
    join read_csv_auto('{h}/patients.csv.gz') p using (subject_id)
    where a.insurance = 'Medicare'
    """)
    con.execute(f"""
    create or replace table pool as
    with dx1 as (
      select d.hadm_id, d.icd_code, d.icd_version, t.long_title as primary_dx_title,
             {cohort.DX_CATEGORY} as dx_category
      from read_csv_auto('{h}/diagnoses_icd.csv.gz', types = {{'icd_code': 'VARCHAR'}}) d
      left join read_csv_auto('{h}/d_icd_diagnoses.csv.gz', types = {{'icd_code': 'VARCHAR'}}) t
        using (icd_code, icd_version)
      where d.seq_num = 1
    ),
    joint as (
      select distinct hadm_id from read_csv_auto('{h}/procedures_icd.csv.gz', types = {{'icd_code': 'VARCHAR'}})
      where {cohort.JOINT_PROC}
    ),
    obs_unit as (select distinct hadm_id from read_csv_auto('{h}/transfers.csv.gz') where careunit = 'Observation'),
    icu as (select distinct hadm_id from read_csv_auto('{i}/icustays.csv.gz')),
    poe as (
      select hadm_id,
             bool_or(order_type = 'Consults' and order_subtype = 'Physical Therapy') as pt_consult,
             bool_or((order_type = 'General Care' and order_subtype = 'Wound Care')
                     or (order_type = 'Nutrition' and order_subtype = 'Tubefeeding Order')
                     or (order_type = 'TPN')) as skilled_nursing_order
      from read_csv_auto('{h}/poe.csv.gz')
      where order_type in ('Consults', 'General Care', 'Nutrition', 'TPN')
      group by hadm_id
    ),
    abx as (
      select distinct hadm_id
      from read_csv_auto('{h}/prescriptions.csv.gz')
      where route ilike 'IV%' and regexp_matches(lower(drug), '{IV_ANTIBIOTICS}')
        and date_diff('day', starttime, stoptime) >= 5
    ),
    prior as (
      select distinct cur.hadm_id
      from adm cur join adm prev
        on prev.subject_id = cur.subject_id and prev.hadm_id <> cur.hadm_id
       and prev.dischtime <= cur.admittime and prev.dischtime >= cur.admittime - interval 30 day
       and prev.midnights >= {C.MIN_MIDNIGHTS}
    )
    select adm.subject_id, adm.hadm_id, adm.admittime, adm.dischtime, adm.admission_type,
           adm.admission_location, adm.discharge_location, adm.race, adm.language, adm.marital_status,
           adm.gender, adm.age_at_admit, adm.midnights,
           dx1.icd_code, dx1.icd_version, dx1.primary_dx_title,
           case when dx1.dx_category = 'hip_fracture' then 'hip_fracture'
                when joint.hadm_id is not null then 'joint_replacement'
                else dx1.dx_category end as category,
           (adm.admission_type ilike '%OBSERVATION%' or obs_unit.hadm_id is not null) as observation,
           (icu.hadm_id is not null) as had_icu,
           coalesce(poe.pt_consult, false) as pt_consult,
           coalesce(poe.skilled_nursing_order, false) as skilled_nursing_order,
           (abx.hadm_id is not null) as iv_antibiotic_5d,
           (prior.hadm_id is not null) as prior_qual_stay,
           ni.note_id
    from adm
    join notes_index ni using (hadm_id)
    left join dx1 using (hadm_id)
    left join joint using (hadm_id)
    left join obs_unit using (hadm_id)
    left join icu using (hadm_id)
    left join poe using (hadm_id)
    left join abx using (hadm_id)
    left join prior using (hadm_id)
    where adm.age_at_admit >= {C.MIN_AGE} and adm.hospital_expire_flag = 0
      and adm.discharge_location in ('{SNF}', '{HHC}', '{HOME}', '{REHAB}')
    """)


def draw(con, scenario: str, where: str, location: str, k: int) -> pl.DataFrame:
    """k patients for one (scenario, discharge_location) cell, skipping patients in table `used`.

    One admission per patient is picked with one salted hash and patients are ranked with another, so
    patients with many admissions are not favoured. Rank position % 5 in TEST_POSITIONS -> test, as in
    sample_cases1.csv.
    """
    test_pos = ", ".join(str(p) for p in C.TEST_POSITIONS)
    return con.sql(f"""
    with cell as (
      select * from pool
      where discharge_location = ? and ({where})
        and subject_id not in (select subject_id from used)
      qualify row_number() over (partition by subject_id order by md5(hadm_id::VARCHAR || ':pick:{C.SEED}')) = 1
    ),
    ranked as (
      select *, row_number() over (order by md5(subject_id::VARCHAR || ':{scenario}:{C.SEED}')) as rn from cell
    )
    select *, '{scenario}' as scenario,
           case when rn % {C.TEST_MODULUS} in ({test_pos}) then 'test' else 'dev' end as split
    from ranked where rn <= {int(k)}
    """, params=[location]).pl()


def main() -> None:
    con = cohort.connect()
    print("building pool (scans discharge notes, poe and prescriptions)...")
    build_pool(con)
    con.execute(f"create table used as select distinct subject_id::BIGINT as subject_id "
                f"from read_csv('{C.sql_path(MAIN)}', header = true, all_varchar = true)")

    parts = []
    for scenario, (where, quotas) in SCENARIOS.items():
        for location, k in quotas.items():
            df = draw(con, scenario, where, location, k)
            if df.height < k:
                print(f"  short: {scenario} / {location}: {df.height} of {k}")
            parts.append(df)
            con.register("picked", df.select("subject_id"))
            con.execute("insert into used select subject_id from picked")

    supp = pl.concat(parts).select(
        "subject_id", "hadm_id", "note_id", "scenario",
        pl.col("category").fill_null("other"),
        (pl.col("discharge_location") == SNF).cast(pl.Int32).alias("label_snf"),
        "discharge_location", "split", pl.lit(BATCH).alias("batch"),
        "admission_type", "admission_location", "age_at_admit", "gender", "race", "language", "marital_status",
        pl.col("midnights").alias("inpatient_midnights"), "observation", "prior_qual_stay", "had_icu",
        "pt_consult", "skilled_nursing_order", "iv_antibiotic_5d",
        pl.col("icd_code").alias("primary_icd_code"), pl.col("icd_version").alias("primary_icd_version"),
        "primary_dx_title", "admittime", "dischtime",
    ).sort("scenario", "discharge_location", "hadm_id")
    supp.write_parquet(OUT.with_suffix(".parquet"))
    supp.write_csv(OUT.with_suffix(".csv"))

    cohort.export_notes(con, supp["note_id"].cast(pl.String).to_list(), NOTES_OUT)

    n_notes = con.execute(f"select count(*) from read_parquet('{C.sql_path(NOTES_OUT)}')").fetchone()[0]
    print(f"supplement cases: {supp.height}; notes exported: {n_notes}")
    print(supp.group_by("scenario", "discharge_location", "split").len().sort(pl.all()))
    print(supp.group_by("category").len().sort(pl.all()))


if __name__ == "__main__":
    main()
