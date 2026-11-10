"""Generated dev CaseBundles (data/sample/case_bundles/dev): step-③ completion checks."""
import csv
import json
from pathlib import Path

import pytest

from snf_pa.adapters.sources import discharge_note as dn
from snf_pa.schemas import FORBIDDEN_FIELDS, CaseBundle

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "data" / "sample" / "case_bundles" / "dev"
FILES = sorted(DIR.glob("*.json"))
PARQUET_READY = (ROOT / "data" / "derived" / "parquet" / "poe.parquet").exists()

pytestmark = pytest.mark.skipif(not FILES, reason="dev bundles not built")


@pytest.fixture(scope="module")
def bundles():
    return [CaseBundle.model_validate_json(f.read_text(encoding="utf-8")) for f in FILES]


def test_one_bundle_per_dev_case(bundles):
    with (ROOT / "data" / "splits" / "dev_cases.csv").open(encoding="utf-8") as f:
        dev = {r["hadm_id"] for r in csv.DictReader(f)}
    assert {b.case_id for b in bundles} == dev
    with (ROOT / "data" / "splits" / "test_cases.csv").open(encoding="utf-8") as f:
        assert not {b.case_id for b in bundles} & {r["hadm_id"] for r in csv.DictReader(f)}


def test_hash_matches_content(bundles):
    for b in bundles:
        assert b.content_hash == b.compute_hash()


def test_evidence_available_before_t_pa(bundles):
    for b in bundles:
        for e in b.evidence:
            if e.available_at is not None:
                assert e.available_at <= b.timeline.t_pa, (b.case_id, e.ref_id)
            else:
                assert e.source == "discharge_note"      # the only source without a timestamp (design §15)


def test_timeline_points_not_after_t_pa(bundles):
    for b in bundles:
        t = b.timeline
        for name in ("admittime", "ed_intime", "ed_outtime", "observation_order_time", "inpatient_order_time",
                     "inpatient_start"):
            v = getattr(t, name)
            assert v is None or v <= t.t_pa, (b.case_id, name)
        for p in t.prior_stays_30d:
            assert p.dischtime <= t.t_pa and (t.dischtime - p.dischtime).days <= 30, (b.case_id, p.hadm_id)


def test_ids_unique_and_well_formed(bundles):
    for b in bundles:
        ids = [e.ref_id for e in b.evidence]
        assert len(ids) == len(set(ids))
        assert all(i.startswith(("DS:", "RAD:", "POE:", "RX:")) for i in ids)


def test_no_forbidden_or_label_fields(bundles):
    for f in FILES:
        keys = set()

        def walk(x):
            if isinstance(x, dict):
                keys.update(x)
                for v in x.values():
                    walk(v)
            elif isinstance(x, list):
                for v in x:
                    walk(v)
        walk(json.loads(f.read_text(encoding="utf-8")))
        assert not keys & FORBIDDEN_FIELDS
    for b in bundles:
        for e in b.evidence:      # condition tags are coded after discharge: never on evidence
            assert not set(e.needs) & {"hip_fracture", "acute_stroke", "pressure_ulcer", "dementia", "parkinson", "debility"}


def test_no_dropped_sections_and_no_residual(bundles):
    for b in bundles:
        spans = [dn.Span(e.ref_id, e.section, 0, 0, e.text) for e in b.evidence if e.source == "discharge_note"]
        assert not {s.section for s in spans} & dn.DROP
        broad = dn.BROAD | ({"PR"} if not any(s.section == "HC" for s in spans) else set())
        assert dn.residual(spans, broad) == [], b.case_id


def test_assumptions_declared(bundles):
    for b in bundles:
        assert set(b.assumed) == {"C2", "C7", "C8"}
        assert "pt_ot_evaluation_note" in b.missing


@pytest.mark.skipif(not PARQUET_READY, reason="Parquet subset not built on this machine")
def test_rebuild_is_identical(tmp_path, bundles):
    from snf_pa.adapters import mimic
    again = {b.case_id: b.content_hash for b in mimic.build("dev", tmp_path)}
    assert again == {b.case_id: b.content_hash for b in bundles}
