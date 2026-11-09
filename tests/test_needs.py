"""Need-reason catalog: schema rules, and tagging on a tiny synthetic Parquet set (no MIMIC data)."""
from datetime import datetime

import duckdb
import pytest

from snf_pa import needs as needs_mod
from snf_pa.registry import NeedCatalog, load_needs


def test_catalog_loads_and_is_consistent():
    cat = load_needs()
    assert cat.version >= 1 and cat.needs
    ids = [n.id for n in cat.needs]
    assert len(ids) == len(set(ids))
    for n in cat.needs:
        if n.rule.type == "diagnosis":
            assert n.available_before_t_pa is False   # ICD codes are coded after discharge
        if n.kind == "service":
            assert n.policy_refs and all(r.startswith("42 CFR 409.33") for r in n.policy_refs)


def test_diagnosis_rule_cannot_claim_t_pa_availability():
    bad = {"version": 1, "needs": [{"id": "x", "name": "x", "kind": "condition", "policy_refs": [],
                                    "available_before_t_pa": True,
                                    "rule": {"type": "diagnosis", "icd10": ["L89"]}}]}
    with pytest.raises(ValueError):
        NeedCatalog.model_validate(bad)


@pytest.fixture()
def tiny(tmp_path, monkeypatch):
    """Admissions 1-4, all 2150-01-01 .. 2150-01-10, so T_pa = 2150-01-09 00:00 and T_pa - 48h = 01-07 00:00."""
    con = duckdb.connect()
    t = lambda s: datetime.fromisoformat(s)
    con.execute("create table poe (hadm_id BIGINT, ordertime TIMESTAMP, order_type VARCHAR, order_subtype VARCHAR, transaction_type VARCHAR)")
    con.executemany("insert into poe values (?,?,?,?,?)", [
        (1, t("2150-01-03"), "Consults", "Physical Therapy", "New"),        # before T_pa -> rehab_therapy
        (1, t("2150-01-09 12:00"), "General Care", "Wound Care", "New"),    # after T_pa -> not counted
        (1, t("2150-01-04"), "Respiratory", "Oxygen Therapy", "D/C"),       # not a New order
        (2, t("2149-12-31"), "Consults", "Physical Therapy", "New"),        # before admission -> not counted
        (3, t("2150-01-09"), "Consults", "Occupational Therapy", "New"),    # exactly at T_pa -> counted
    ])
    con.execute("create table prescriptions (hadm_id BIGINT, starttime TIMESTAMP, stoptime TIMESTAMP, drug VARCHAR, route VARCHAR)")
    con.executemany("insert into prescriptions values (?,?,?,?,?)", [
        (1, t("2150-01-05"), t("2150-01-12"), "Vancomycin", "IV"),          # active at T_pa -> iv_therapy
        (1, t("2150-01-02"), t("2150-01-03"), "CefTRIAXone", "IV"),         # stopped >48h before T_pa
        (1, t("2150-01-05"), None, "Ciprofloxacin", "PO"),                  # oral
        (2, t("2150-01-02"), t("2150-01-07"), "Cefazolin", "IV"),           # stops exactly at T_pa-48h -> counted
        (3, t("2150-01-02"), t("2150-01-06 23:59"), "Cefazolin", "IV"),     # stops 1 min earlier -> not counted
        (3, t("2150-01-09 01:00"), t("2150-01-10"), "Vancomycin", "IV"),    # starts after T_pa -> not counted
        (4, t("2150-01-08"), t("2150-01-10"), "Vancomycin", "PB"),          # piggyback route -> counted
    ])
    con.execute("create table diagnoses_icd (hadm_id BIGINT, seq_num INT, icd_code VARCHAR, icd_version INT)")
    con.executemany("insert into diagnoses_icd values (?,?,?,?)", [
        (1, 1, "N390", 10), (1, 7, "L89153", 10),
        (2, 3, "S72001D", 10),   # hip fracture, subsequent encounter -> not hip_fracture
        (3, 2, "S72001A", 10),   # hip fracture, initial encounter -> hip_fracture
        (4, 4, "82020", 9),      # ICD-9 hip fracture -> hip_fracture
    ])
    for tbl in ("poe", "prescriptions", "diagnoses_icd"):
        con.execute(f"copy {tbl} to '{(tmp_path / (tbl + '.parquet')).as_posix()}' (format parquet)")
    monkeypatch.setattr(needs_mod, "PARQUET", tmp_path)
    con.execute("""create table adm as select unnest([1, 2, 3, 4])::BIGINT hadm_id,
                   timestamp '2150-01-01' admittime, timestamp '2150-01-10' dischtime""")
    return con


def test_tagging_respects_rules_and_t_pa(tiny):
    needs_mod.tag_admissions(tiny, "adm")
    got = {}
    for h, n in tiny.execute("select hadm_id, need_id from need_tags").fetchall():
        got.setdefault(h, set()).add(n)
    assert got[1] == {"rehab_therapy", "iv_therapy", "pressure_ulcer"}
    assert got[2] == {"iv_therapy"}
    assert got[3] == {"rehab_therapy", "hip_fracture"}
    assert got[4] == {"iv_therapy", "hip_fracture"}
