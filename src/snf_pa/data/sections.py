"""Step 2: split a MIMIC-IV discharge summary into its top-level sections.

Top-level headers in MIMIC-IV-Note sit alone on their own line, at column 0, ending with ':'.
Sub-headers inside a section (e.g. 'TRANSITIONAL ISSUES:') stay part of that section.
"""
import re
from dataclasses import dataclass

# Canonical code -> header text. Order follows the note template; text before the first
# matched header goes to HDR (name, dates, service, allergies, attending).
SECTION_HEADERS = {
    "CC": "Chief Complaint",
    "PROC": "Major Surgical or Invasive Procedure",
    "HPI": "History of Present Illness",
    "PMH": "Past Medical History",
    "SH": "Social History",
    "FH": "Family History",
    "PE": "Physical Exam",
    "PR": "Pertinent Results",
    "HC": "Brief Hospital Course",
    "MEDADM": "Medications on Admission",
    "MEDDC": "Discharge Medications",
    "DISPO": "Discharge Disposition",
    "FAC": "Facility",
    "DXDC": "Discharge Diagnosis",
    "COND": "Discharge Condition",
    "DCI": "Discharge Instructions",
    "FU": "Followup Instructions",
}
_BY_TEXT = {v.lower(): k for k, v in SECTION_HEADERS.items()}
HEADER_RE = re.compile(
    r"^(" + "|".join(re.escape(h) for h in SECTION_HEADERS.values()) + r"):[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True)
class Section:
    code: str
    start: int  # first character of the section body in the original text
    end: int    # one past the last character


def split_sections(text: str) -> list[Section]:
    """Return sections in document order; bodies exclude the header line itself.

    A header seen a second time (rare: copy-forward) starts a new section with the same code.
    """
    out: list[Section] = []
    cur_code, cur_start = "HDR", 0
    for m in HEADER_RE.finditer(text):
        out.append(Section(cur_code, cur_start, m.start()))
        cur_code, cur_start = _BY_TEXT[m.group(1).lower()], m.end()
    out.append(Section(cur_code, cur_start, len(text)))
    return [s for s in out if text[s.start:s.end].strip()]
