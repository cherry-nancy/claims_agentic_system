"""CaseBundle: the only input of the review pipeline (design v8 §3.3).

Hard rule 2 / 10 (and decision_log D-006): fields that are known only after discharge or that are labels
(discharge location, sampling scenario, diagnosis-derived need tags, DRG) must never appear here.
`extra="forbid"` makes any unknown field an error.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

FORBIDDEN_FIELDS = {"discharge_location", "scenario", "label_snf", "drg", "drg_code", "hospital_expire_flag",
                    "discharge_diagnosis", "discharge_medications", "needs_conditions"}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Demographics(_Strict):
    age_at_admit: int
    sex: str | None
    insurance: str


class PriorStay(_Strict):
    hadm_id: int
    admittime: datetime
    dischtime: datetime
    inpatient_start: datetime
    inpatient_start_source: Literal["poe_admit_inpatient", "admittime_fallback"]
    midnights: int


class Timeline(_Strict):
    # Every time point is <= t_pa or None (hard rule 2), except dischtime: the planned discharge date is part of
    # the PA request and C1 needs it (design §3.1 note 3).
    admittime: datetime | None
    dischtime: datetime
    ed_intime: datetime | None
    ed_outtime: datetime | None
    observation_order_time: datetime | None
    inpatient_order_time: datetime | None
    inpatient_start: datetime
    inpatient_start_source: Literal["poe_admit_inpatient", "admittime_fallback"]
    t_pa: datetime
    prior_stays_30d: list[PriorStay]


class EvidenceItem(_Strict):
    ref_id: str
    source: str
    kind: Literal["span", "fact"]
    section: str | None = None
    available_at: datetime | None = None
    text: str
    provenance: str
    needs: list[str] = Field(default_factory=list)


class CaseBundle(_Strict):
    case_id: str
    content_hash: str = ""
    demographics: Demographics
    timeline: Timeline
    evidence: list[EvidenceItem]
    sources: dict[str, str]
    assumed: dict[str, str]
    missing: list[str]

    def compute_hash(self) -> str:
        body = self.model_dump(mode="json", exclude={"content_hash"})
        return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def sealed(self) -> "CaseBundle":
        return self.model_copy(update={"content_hash": self.compute_hash()})
