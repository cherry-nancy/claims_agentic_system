"""Radiology impressions and fact cards: T_pa boundaries on synthetic rows."""
from datetime import datetime

import duckdb

from snf_pa.adapters.sources import facts, radiology
from snf_pa.registry import load_needs

D = datetime.fromisoformat
T_PA = D("2150-01-09 00:00")
REPORT = """EXAMINATION: CHEST (PA AND LAT)

FINDINGS:
Mild cardiomegaly.

IMPRESSION:
1. No acute cardiopulmonary process. Small left effusion.

RECOMMENDATION(S): none
"""


def test_impression_only_and_signed_before_t_pa():
    ev = radiology.to_evidence("R1", REPORT, D("2150-01-08 23:59"), T_PA)
    assert [e.ref_id for e in ev] == ["RAD:R1:s1", "RAD:R1:s2"]
    assert "cardiomegaly" not in " ".join(e.text for e in ev) and "none" not in ev[-1].text
    assert radiology.to_evidence("R1", REPORT, T_PA, T_PA)                      # exactly at T_pa: available
    assert radiology.to_evidence("R1", REPORT, D("2150-01-09 00:01"), T_PA) == []   # signed after T_pa
    assert radiology.to_evidence("R2", "FINDINGS: x\n", D("2150-01-02"), T_PA) == []


def _con(tmp_path):
    c = duckdb.connect()
    # inpatient order placed in the ED at 2149-12-31 20:00, ED arrival 18:00, admittime next morning
    c.execute("create temp table case_tl as select 1::BIGINT hadm_id, timestamp '2150-01-01' admittime, "
              "timestamp '2150-01-10' dischtime, timestamp '2150-01-09' t_pa, "
              "timestamp '2149-12-31 20:00' inpatient_start, timestamp '2149-12-31 18:00' ed_intime")
    c.execute("create table poe (poe_id VARCHAR, hadm_id BIGINT, ordertime TIMESTAMP, order_type VARCHAR, order_subtype VARCHAR, transaction_type VARCHAR)")
    c.executemany("insert into poe values (?,?,?,?,?,?)", [
        ("p0", 1, D("2149-12-31 22:00"), "Consults", "Speech/Swallowing", "New"),    # boarding in ED: counted
        ("p1", 1, D("2150-01-02"), "Consults", "Physical Therapy", "New"),
        ("p2", 1, D("2150-01-09 00:00"), "Consults", "Physical Therapy", "New"),     # at T_pa: counted
        ("p3", 1, D("2150-01-09 00:01"), "Consults", "Occupational Therapy", "New"),  # after: excluded
        ("p4", 1, D("2150-01-05"), "General Care", "Wound Care", "Change")])         # not New
    c.execute("create table rx (pharmacy_id BIGINT, hadm_id BIGINT, starttime TIMESTAMP, stoptime TIMESTAMP, drug VARCHAR, route VARCHAR)")
    c.executemany("insert into rx values (?,?,?,?,?,?)", [
        (10, 1, D("2150-01-07"), D("2150-01-12"), "Vancomycin", "IV"),
        (11, 1, D("2150-01-09 01:00"), D("2150-01-12"), "Vancomycin", "IV"),          # starts after T_pa
        (12, 1, D("2150-01-02"), D("2150-01-03"), "Cefazolin", "IV")])                # stopped > 48 h before
    c.execute(f"copy poe to '{(tmp_path / 'poe.parquet').as_posix()}' (format parquet)")
    c.execute(f"copy rx to '{(tmp_path / 'rx.parquet').as_posix()}' (format parquet)")
    return c


def test_fact_cards_respect_t_pa(tmp_path):
    c, cat = _con(tmp_path), load_needs()
    poe = facts.poe_facts(c, tmp_path / "poe.parquet", cat)[1]
    assert sorted(e.ref_id for e in poe) == ["POE:rehab_therapy", "POE:speech_therapy"]
    poe = [e for e in poe if e.ref_id == "POE:rehab_therapy"]
    assert poe[0].text.startswith("Physical Therapy: 2 order(s)") and poe[0].available_at == T_PA
    rx = facts.rx_facts(c, tmp_path / "rx.parquet", cat)[1]
    assert [e.ref_id for e in rx] == ["RX:iv_therapy:vancomycin"]
    assert "1 order(s)" in rx[0].text and "still active" in rx[0].text
    assert rx[0].provenance == "prescriptions:drug=vancomycin;pharmacy_id=10"
    for e in poe + rx:
        assert e.available_at <= T_PA and e.needs
