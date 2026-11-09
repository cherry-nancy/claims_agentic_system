"""Apply the need-reason catalog (knowledge/needs.yaml) to admissions in the Parquet subset.

    tag_admissions(con, "adm") -> creates temp table `need_tags(hadm_id, need_id)`

`adm` must have hadm_id, admittime, dischtime. T_pa here is the provisional form
max(dischtime - 24h, admittime) (design §3.1 note 6); the adapter (step ③) replaces admittime with the
inpatient-order start. Diagnosis rules ignore time (they are flagged available_before_t_pa: false and are
used only for sampling / reporting).
"""
from __future__ import annotations

import duckdb

from snf_pa.paths import ROOT, sql_path
from snf_pa.registry import DiagnosisRule, IvDrugRule, NeedCatalog, PoeOrderRule, load_needs

PARQUET = ROOT / "data" / "derived" / "parquet"


def _q(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def _sql(need_id: str, rule, adm: str) -> str:
    t_pa = "greatest(a.dischtime - interval 24 hour, a.admittime)"
    if isinstance(rule, PoeOrderRule):
        pairs = " or ".join(f"(p.order_type = {_q(t)} and p.order_subtype = {_q(s)})" for t, s in rule.orders)
        return f"""select distinct a.hadm_id, {_q(need_id)} as need_id
                   from {adm} a join '{sql_path(PARQUET / 'poe.parquet')}' p using (hadm_id)
                   where p.transaction_type = 'New' and ({pairs})
                     and p.ordertime >= a.admittime and p.ordertime <= {t_pa}"""
    if isinstance(rule, IvDrugRule):
        routes = ", ".join(_q(r) for r in rule.routes)
        return f"""select distinct a.hadm_id, {_q(need_id)} as need_id
                   from {adm} a join '{sql_path(PARQUET / 'prescriptions.parquet')}' r using (hadm_id)
                   where r.route in ({routes}) and regexp_matches(lower(r.drug), {_q(rule.drug_regex)})
                     and r.starttime <= {t_pa}
                     and coalesce(r.stoptime, a.dischtime) >= {t_pa} - interval {rule.active_within_hours} hour"""
    if isinstance(rule, DiagnosisRule):
        seventh = (" and substr(d.icd_code, 7, 1) in (" + ", ".join(_q(s) for s in rule.icd10_seventh) + ")"
                   if rule.icd10_seventh else "")
        conds = [f"(d.icd_version = 10 and starts_with(d.icd_code, {_q(c)}){seventh})" for c in rule.icd10]
        conds += [f"(d.icd_version = 9 and starts_with(d.icd_code, {_q(c)}))" for c in rule.icd9]
        return f"""select distinct a.hadm_id, {_q(need_id)} as need_id
                   from {adm} a join '{sql_path(PARQUET / 'diagnoses_icd.parquet')}' d using (hadm_id)
                   where {" or ".join(conds)}"""
    raise TypeError(f"unknown rule for {need_id}")


def tag_admissions(con: duckdb.DuckDBPyConnection, adm: str, catalog: NeedCatalog | None = None) -> NeedCatalog:
    cat = catalog or load_needs()
    union = "\nunion all\n".join(_sql(n.id, n.rule, adm) for n in cat.needs)
    con.execute(f"create or replace temp table need_tags as {union}")
    return cat
