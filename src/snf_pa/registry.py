"""Registries (design §2.1). Step ② only needs the need-reason catalog; criteria and sources come later."""
from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from snf_pa.paths import ROOT

NEEDS_FILE = ROOT / "knowledge" / "needs.yaml"


class PoeOrderRule(BaseModel):
    type: Literal["poe_order"]
    orders: list[tuple[str, str]] = Field(min_length=1)


class IvDrugRule(BaseModel):
    type: Literal["iv_drug"]
    routes: list[str] = Field(min_length=1)
    drug_regex: str
    active_within_hours: int = Field(gt=0)


class DiagnosisRule(BaseModel):
    type: Literal["diagnosis"]
    icd10: list[str] = []
    icd9: list[str] = []
    # ICD-10-CM 7th character filter for injury codes, e.g. ["A", "B", "C"] = initial encounter only
    # (excludes subsequent-encounter D/G/K and sequela S codes).
    icd10_seventh: list[str] = []

    @model_validator(mode="after")
    def _some_codes(self):
        if not (self.icd10 or self.icd9):
            raise ValueError("diagnosis rule needs at least one code prefix")
        return self


class Need(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    name: str
    kind: Literal["service", "condition"]
    policy_refs: list[str]
    available_before_t_pa: bool
    rule: PoeOrderRule | IvDrugRule | DiagnosisRule = Field(discriminator="type")
    synonyms: list[str] = []

    @model_validator(mode="after")
    def _consistent(self):
        # ICD codes are assigned after discharge: a diagnosis rule can never be T_pa-available evidence.
        if self.rule.type == "diagnosis" and self.available_before_t_pa:
            raise ValueError(f"{self.id}: diagnosis rules are not available before T_pa")
        if self.kind == "service" and not self.policy_refs:
            raise ValueError(f"{self.id}: a service need must cite the policy section it maps to")
        return self


class NeedCatalog(BaseModel):
    version: int
    needs: list[Need]
    content_hash: str = ""

    @model_validator(mode="after")
    def _unique(self):
        ids = [n.id for n in self.needs]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate need ids")
        return self

    def get(self, need_id: str) -> Need:
        return next(n for n in self.needs if n.id == need_id)


SOURCES_FILE = ROOT / "knowledge" / "sources.yaml"


class Source(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    tables: list[str] = Field(min_length=1)
    t_pa_field: str
    leakage: str
    evidence_kind: Literal["span", "fact"]
    id_format: str
    module: str


class SourceRegistry(BaseModel):
    version: int
    sources: list[Source]
    content_hash: str = ""

    @model_validator(mode="after")
    def _unique(self):
        ids = [s.id for s in self.sources]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate source ids")
        return self


@lru_cache(maxsize=4)
def load_sources(path: Path = SOURCES_FILE) -> SourceRegistry:
    raw = path.read_bytes()
    reg = SourceRegistry.model_validate(yaml.safe_load(raw))
    reg.content_hash = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()[:12]
    return reg


@lru_cache(maxsize=4)
def load_needs(path: Path = NEEDS_FILE) -> NeedCatalog:
    raw = path.read_bytes()
    cat = NeedCatalog.model_validate(yaml.safe_load(raw))
    cat.content_hash = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()[:12]
    return cat
