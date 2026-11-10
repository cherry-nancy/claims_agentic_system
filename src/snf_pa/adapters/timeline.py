"""Timeline and T_pa (design v8 §3.1 note 3, §3.4).

Inpatient start = earliest ADT order whose detail 'Admit category' = 'Admit to inpatient'. MIMIC records an
observation-to-inpatient conversion as a 'Change' transaction, so New and Change orders both count (New-only
misses most conversions; see reports/step3_adapter.md). Order subtypes Admit / Transfer / Postop are used;
'Discharge' orders also carry the category but are placed at discharge, after T_pa, so they are never used as
the inpatient start (they are only included when reproducing the Appendix A counts).
No inpatient order -> fall back to admittime and flag it (design §3.4, §6.2: C1 then gives bounds).

T_pa = max(dischtime - 24h, inpatient_start).

The connection must have views `admissions`, `poe`, `poe_detail`, `edstays` (Parquet subset or raw tables).
"""
from __future__ import annotations

import duckdb

from snf_pa.paths import ROOT, sql_path

PARQUET = ROOT / "data" / "derived" / "parquet"
INPATIENT_SUBTYPES = ("Admit", "Transfer", "Postop")
APPENDIX_A_SUBTYPES = ("Admit", "Transfer", "Postop", "Discharge")


def register_parquet(con: duckdb.DuckDBPyConnection) -> None:
    for t in ("admissions", "poe", "poe_detail", "edstays"):
        con.execute(f"create or replace view {t} as select * from '{sql_path(PARQUET / (t + '.parquet'))}'")


def build_timeline(con: duckdb.DuckDBPyConnection, hadm_table: str = "admissions",
                   subtypes: tuple[str, ...] = INPATIENT_SUBTYPES) -> None:
    """Temp table `timeline`, one row per admission in `hadm_table` (needs hadm_id)."""
    subs = ", ".join(f"'{s}'" for s in subtypes)
    con.execute(f"""
        create or replace temp table timeline as
        with cat as (
            select p.hadm_id, p.ordertime, p.order_subtype, d.field_value as category
            from poe p join poe_detail d using (poe_id)
            where p.order_type = 'ADT orders' and d.field_name = 'Admit category'
              and p.transaction_type in ('New', 'Change')
              and p.hadm_id in (select hadm_id from {hadm_table})
        ), ord as (
            select hadm_id,
                   min(ordertime) filter (where category = 'Admit to inpatient' and order_subtype in ({subs})) as inp,
                   min(ordertime) filter (where category = 'Place in observation') as obs
            from cat group by 1
        ), ed as (
            select hadm_id, min(intime) as ed_in, max(outtime) as ed_out from edstays group by 1
        )
        select a.hadm_id, a.subject_id, a.admittime, a.dischtime,
               ed.ed_in as ed_intime, ed.ed_out as ed_outtime,
               ord.obs as observation_order_time, ord.inp as inpatient_order_time,
               coalesce(ord.inp, a.admittime) as inpatient_start,
               case when ord.inp is null then 'admittime_fallback' else 'poe_admit_inpatient' end
                   as inpatient_start_source,
               greatest(a.dischtime - interval 24 hour, coalesce(ord.inp, a.admittime)) as t_pa,
               date_diff('day', coalesce(ord.inp, a.admittime)::date, a.dischtime::date) as midnights
        from admissions a
        left join ord using (hadm_id) left join ed using (hadm_id)
        where a.hadm_id in (select hadm_id from {hadm_table})
    """)


def prior_stays(con: duckdb.DuckDBPyConnection) -> None:
    """Temp table `prior_stays`: for each timeline row, the same patient's earlier stays discharged within the
    30 days before the CURRENT discharge. 42 CFR 409.30(b)(1): the SNF admission must be within 30 calendar days
    after discharge from the qualifying stay; the SNF admission is taken as the current discharge (C2 is assumed,
    CaseBundle.assumed). Anchoring on the current admission instead would list stays that cannot qualify (found in
    the step-3 independent review). Also capped at T_pa. Needs `timeline` over ALL of the patient's admissions."""
    con.execute("""
        create or replace temp table prior_stays as
        select cur.hadm_id, p.hadm_id as prior_hadm_id, p.admittime, p.dischtime, p.inpatient_start,
               p.inpatient_start_source, p.midnights
        from timeline cur join timeline p
          on p.subject_id = cur.subject_id and p.hadm_id != cur.hadm_id
         and p.dischtime <= cur.admittime and p.dischtime <= cur.t_pa
         and p.dischtime >= cur.dischtime - interval 30 day
    """)
