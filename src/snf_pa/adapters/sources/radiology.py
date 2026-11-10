"""Radiology reports -> span evidence (design v8 §3.5: IMPRESSION only).

A report exists once it is signed: available_at = storetime, kept only if storetime <= T_pa
(time rule adopted from cfeng, origin/cfeng @ 3b279cc imaging.py L65/L164; cut-off here is the design T_pa).
Sentence splitting reuses the discharge-note splitter. IDs: RAD:<note_id>:s<n>, numbered over the impression.
"""
from __future__ import annotations

import re
from datetime import datetime

from snf_pa.adapters.sources.discharge_note import sentences
from snf_pa.schemas import EvidenceItem

SOURCE_ID = "radiology"
IMPRESSION = re.compile(r"(?mi)^[ \t]*IMPRESSION:[ \t]*")
NEXT_HEADER = re.compile(r"(?m)^[ \t]*[A-Z][A-Z /&()-]{2,40}:")


def impression_bounds(text: str) -> tuple[int, int] | None:
    m = IMPRESSION.search(text)
    if not m:
        return None
    nxt = NEXT_HEADER.search(text, m.end())
    return m.end(), (nxt.start() if nxt else len(text))


def to_evidence(note_id: str, text: str, storetime: datetime, t_pa: datetime) -> list[EvidenceItem]:
    if storetime is None or storetime > t_pa:
        return []
    b = impression_bounds(text)
    if not b:
        return []
    out = []
    for i, (s, e) in enumerate(sentences(text, *b), 1):
        out.append(EvidenceItem(ref_id=f"RAD:{note_id}:s{i}", source=SOURCE_ID, kind="span", section="IMPRESSION",
                                available_at=storetime, text=re.sub(r"\s+", " ", text[s:e]).strip(),
                                provenance=f"radiology:note_id={note_id}:chars={s}-{e}"))
    return out
