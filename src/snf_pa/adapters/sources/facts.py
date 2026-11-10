"""Fact cards from orders and prescriptions (design v8 §3.6), one per service need in knowledge/needs.yaml.

Quantified, not yes/no (§3.6). Only rows that exist at T_pa are used (orders: ordertime <= T_pa;
prescriptions: starttime <= T_pa). available_at = the latest such row's time. Condition needs (ICD codes) are
never turned into facts: they are coded after discharge (hard rule 2).

IDs: POE:<need_id> (one card per order-based need), RX:<need_id>:<drug> (one card per IV drug).
"""
from __future__ import annotations

import re
from datetime import datetime

import duckdb

from snf_pa.paths import sql_path
from snf_pa.registry import IvDrugRule, NeedCatalog, PoeOrderRule
from snf_pa.schemas import EvidenceItem


def _hours(a: datetime, b: datetime) -> float:
    return round((b - a).total_seconds() / 3600, 1)


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def poe_facts(con: duckdb.DuckDBPyConnection, poe_path, cat: NeedCatalog) -> dict[int, list[EvidenceItem]]:
    """`case_tl` temp table must exist (hadm_id, admittime, t_pa)."""
    out: dict[int, list[EvidenceItem]] = {}
    for need in cat.needs:
        if not isinstance(need.rule, PoeOrderRule):
            continue
        pairs = " or ".join(f"(p.order_type = '{t}' and p.order_subtype = '{s}')" for t, s in need.rule.orders)
        rows = con.execute(f"""
            select t.hadm_id, t.admittime, t.t_pa, count(*), min(p.ordertime), max(p.ordertime),
                   string_agg(distinct p.order_subtype, ', ' order by p.order_subtype),
                   string_agg(p.poe_id, ',' order by p.ordertime)
            from case_tl t join '{sql_path(poe_path)}' p using (hadm_id)
            where p.transaction_type = 'New' and ({pairs}) and p.ordertime <= t.t_pa
              -- from the start of this encounter: ED arrival, or the inpatient order placed while boarding in the
              -- ED (design §3.4), whichever is earliest (step-3 review found orders lost when cut at admittime)
              and p.ordertime >= least(t.admittime, t.inpatient_start, coalesce(t.ed_intime, t.admittime))
            group by all""").fetchall()
        for h, adm, t_pa, n, first, last, subtypes, ids in rows:
            day = (first.date() - adm.date()).days + 1
            text = (f"{subtypes}: {n} order(s) before T_pa; first on hospital day {day}, "
                    f"most recent {_hours(last, t_pa)} h before T_pa.")
            out.setdefault(h, []).append(EvidenceItem(
                ref_id=f"POE:{need.id}", source="poe", kind="fact", available_at=last, text=text,
                provenance=f"poe:poe_id={ids}", needs=[need.id]))
    return out


def rx_facts(con: duckdb.DuckDBPyConnection, rx_path, cat: NeedCatalog) -> dict[int, list[EvidenceItem]]:
    out: dict[int, list[EvidenceItem]] = {}
    for need in cat.needs:
        if not isinstance(need.rule, IvDrugRule):
            continue
        routes = ", ".join(f"'{r}'" for r in need.rule.routes)
        rows = con.execute(f"""
            select t.hadm_id, t.t_pa, lower(r.drug) as drug, count(*), max(r.starttime),
                   bool_or(coalesce(r.stoptime, t.dischtime) >= t.t_pa) as active_at_t_pa,
                   string_agg(r.pharmacy_id::varchar, ',' order by r.starttime)
            from case_tl t join '{sql_path(rx_path)}' r using (hadm_id)
            where r.route in ({routes}) and regexp_matches(lower(r.drug), ?)
              and r.starttime <= t.t_pa
              and coalesce(r.stoptime, t.dischtime) >= t.t_pa - interval {need.rule.active_within_hours} hour
            group by all order by 1, 3""", [need.rule.drug_regex]).fetchall()
        for h, t_pa, drug, n, last_start, active, ids in rows:
            text = (f"IV {drug}: {n} order(s) running at some point in the {need.rule.active_within_hours} h before "
                    f"T_pa; {'still active' if active else 'stopped'} at T_pa; most recent start "
                    f"{_hours(last_start, t_pa)} h before T_pa.")
            # pharmacy_id is not unique in prescriptions (a drug and its diluent share it): drug + pharmacy_id
            out.setdefault(h, []).append(EvidenceItem(
                ref_id=f"RX:{need.id}:{_slug(drug)}", source="prescriptions", kind="fact", available_at=last_start,
                text=text, provenance=f"prescriptions:drug={drug};pharmacy_id={ids}", needs=[need.id]))
    return out
