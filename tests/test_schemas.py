"""CaseBundle schema and data-source registry."""
import importlib.util
from datetime import datetime

import pytest
from pydantic import ValidationError

from snf_pa.registry import load_sources
from snf_pa.schemas import FORBIDDEN_FIELDS, CaseBundle

T = datetime(2150, 1, 1)


def minimal(**extra):
    d = {
        "case_id": "1",
        "demographics": {"age_at_admit": 80, "sex": "F", "insurance": "Medicare"},
        "timeline": {"admittime": T, "dischtime": T, "ed_intime": None, "ed_outtime": None,
                     "observation_order_time": None, "inpatient_order_time": None, "inpatient_start": T,
                     "inpatient_start_source": "admittime_fallback", "t_pa": T, "prior_stays_30d": []},
        "evidence": [{"ref_id": "DS:HC:s1", "source": "discharge_note", "kind": "span", "text": "x",
                      "provenance": "discharge:note_id=1"}],
        "sources": {}, "assumed": {}, "missing": [],
    }
    d.update(extra)
    return d


def test_roundtrip_and_hash_stable():
    b = CaseBundle.model_validate(minimal()).sealed()
    again = CaseBundle.model_validate_json(b.model_dump_json()).sealed()
    assert b.content_hash == again.content_hash and len(b.content_hash) == 64


@pytest.mark.parametrize("field", sorted(FORBIDDEN_FIELDS))
def test_forbidden_fields_rejected(field):
    with pytest.raises(ValidationError):
        CaseBundle.model_validate(minimal(**{field: "x"}))


def test_forbidden_field_in_demographics_rejected():
    d = minimal()
    d["demographics"]["discharge_location"] = "SKILLED NURSING FACILITY"
    with pytest.raises(ValidationError):
        CaseBundle.model_validate(d)


def test_source_registry_consistent():
    reg = load_sources()
    assert {s.id for s in reg.sources} >= {"discharge_note", "radiology", "prescriptions", "poe"}
    for s in reg.sources:
        assert s.t_pa_field                      # every source states how T_pa availability is decided
        assert importlib.util.find_spec(s.module) is not None, f"{s.id}: module {s.module} missing"
