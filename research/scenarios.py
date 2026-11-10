"""Sampling scenarios (design §10.1): admission reason + SNF need tags from knowledge/needs.yaml.

Each admission gets ONE sampling scenario, first match wins:
  1 ortho_postop   need tag hip_fracture, or a hip/knee replacement procedure in the stay
  2 stroke         need tag acute_stroke
  3 wound_iv       need tag wound_care, iv_therapy or pressure_ulcer
  4 heart_failure  primary diagnosis (seq_num = 1) is heart failure - admission reason only, because
                   chronic HF is coded as a comorbidity in ~29% of the pool
  5 medical_decond no surgical service at any point in the stay (services table)
  - other          everything else (surgical stays without the tags above): not sampled
All need tags are kept per admission for reporting (multi-label).

Code-list sources (see reports/teammate_diff_cohort.md items 8-9):
  joint replacement: cfeng origin/cfeng src/snf_pa/data/cohort.py L25-30 (Hui Li's list plus 81.55 removed)
  heart failure:     cfeng origin/cfeng src/snf_pa/data/cohort.py L16-18
Procedure and diagnosis codes are assigned after discharge; they are used here only to choose which cases
enter the evaluation set, never as system input (CLAUDE.md hard rule 2).
"""
from __future__ import annotations

import duckdb

from snf_pa.needs import tag_admissions
from snf_pa.paths import ROOT, sql_path
from snf_pa.registry import NeedCatalog

POOL = ROOT / "data" / "derived" / "cohort" / "pool.parquet"
SPLIT = ROOT / "data" / "splits" / "admissions.csv"   # split by hadm_id (design v9, D-008)
PARQUET = ROOT / "data" / "derived" / "parquet"

SCENARIOS = ("ortho_postop", "stroke", "wound_iv", "heart_failure", "medical_decond")

JOINT_REPLACEMENT_PROC = """((icd_version = 10 and (icd_code like '0SR9%' or icd_code like '0SRB%'
                         or icd_code like '0SRC%' or icd_code like '0SRD%'))
  or (icd_version = 9 and icd_code in ('8151', '8152', '8154')))"""

HEART_FAILURE_DX = """((icd_version = 10 and (icd_code like 'I50%' or icd_code in ('I110', 'I130', 'I132')))
  or (icd_version = 9 and (icd_code like '428%' or icd_code in ('40201', '40211', '40291', '40401',
                           '40403', '40411', '40413', '40491', '40493'))))"""

# A stay is surgical if it was ever under a surgical service. Using `services` (same coding in every year)
# instead of procedure codes: an ICD-9 "operative range" vs ICD-10 root-operation rule classified the same
# bedside procedure (PCI, EGD, dialysis, central line, paracentesis) differently by era and pushed most
# procedure-coded medical stays out of medical_decond (found in the step-2 independent review).
SURGICAL_SERVICES = ("SURG", "ORTHO", "CSURG", "VSURG", "NSURG", "TRAUM", "TSURG", "PSURG", "GU", "GYN", "ENT", "EYE")

BOUNDARY = "(observation_admit_type or naive_midnights < 3 or from_snf)"


def build_candidates(con: duckdb.DuckDBPyConnection) -> NeedCatalog:
    """Temp table `cand`: every pool admission with split, need tags, scenario and boundary flag."""
    con.execute(f"""create or replace temp table adm as
        select p.*, s.split from '{sql_path(POOL)}' p join read_csv('{sql_path(SPLIT)}') s using (hadm_id, subject_id)""")
    cat = tag_admissions(con, "adm")
    proc = sql_path(PARQUET / "procedures_icd.parquet")
    con.execute(f"""create or replace temp table cand as
        with tags as (select hadm_id, list(distinct need_id order by need_id) as needs from need_tags group by 1),
             joint as (select distinct hadm_id from '{proc}' where {JOINT_REPLACEMENT_PROC}),
             oper as (select distinct hadm_id from '{sql_path(PARQUET / "services.parquet")}'
                      where curr_service in ({", ".join(f"'{s}'" for s in SURGICAL_SERVICES)}))
        select a.hadm_id, a.subject_id, a.split, a.discharge_location, a.observation_admit_type,
               a.naive_midnights, a.from_snf, {BOUNDARY} as boundary,
               coalesce(t.needs, []) as needs,
               list_contains(coalesce(t.needs, []), 'hip_fracture') as hip_fracture,
               case
                 when list_contains(coalesce(t.needs, []), 'hip_fracture') or j.hadm_id is not null then 'ortho_postop'
                 when list_contains(coalesce(t.needs, []), 'acute_stroke') then 'stroke'
                 when list_has_any(coalesce(t.needs, []), ['wound_care', 'iv_therapy', 'pressure_ulcer']) then 'wound_iv'
                 when {HEART_FAILURE_DX.replace('icd_code', 'a.primary_icd_code').replace('icd_version', 'a.primary_icd_version')} then 'heart_failure'
                 when o.hadm_id is null then 'medical_decond'
                 else 'other'
               end as scenario
        from adm a left join tags t using (hadm_id) left join joint j using (hadm_id) left join oper o using (hadm_id)
    """)
    return cat
