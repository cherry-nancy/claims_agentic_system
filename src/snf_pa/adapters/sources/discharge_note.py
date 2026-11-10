"""Discharge summary -> span evidence (design v8 §3.3, §3.5).

Adopted from Hui Li, origin/snf-criterion-cards @ 84832e0:
  src/snf_pa/data/sections.py   split_sections()            (unchanged logic)
  src/snf_pa/data/redact.py     sentence splitting, index_note(), two-tier _rule(), clause masking
Changes made on our branch (reports/teammate_diff_redaction.md):
  - sections per design §3.5 / decision_log D-007: drop DISPO, FAC, DCI, FU, DXDC, MEDDC; header keeps only
    Service and Allergies; PROC, FH, MEDADM kept; no "realistic" packet
  - clause masks use "___" (MIMIC's own de-identification token) instead of "[REDACTED-DISPO]"
  - trigger lists extended with cfeng's (origin/cfeng @ 3b279cc, redact.py L84-105): hospice, follow-up
    arrangements, discharge-teaching boilerplate, insurance authorisation
Span IDs are assigned to every sentence of the ORIGINAL note before redaction, so a rule change never renumbers
the sentences that stay (design §3.3).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import pairwise

from snf_pa.schemas import EvidenceItem

SOURCE_ID = "discharge_note"
MASK = "___"

# ---------------------------------------------------------------- sections (Hui Li, sections.py)
SECTION_HEADERS = {
    "CC": "Chief Complaint", "PROC": "Major Surgical or Invasive Procedure", "HPI": "History of Present Illness",
    "PMH": "Past Medical History", "SH": "Social History", "FH": "Family History", "PE": "Physical Exam",
    "PR": "Pertinent Results", "HC": "Brief Hospital Course", "MEDADM": "Medications on Admission",
    "MEDDC": "Discharge Medications", "DISPO": "Discharge Disposition", "FAC": "Facility",
    "DXDC": "Discharge Diagnosis", "COND": "Discharge Condition", "DCI": "Discharge Instructions",
    "FU": "Followup Instructions",
}
_BY_TEXT = {v.lower(): k for k, v in SECTION_HEADERS.items()}
HEADER_RE = re.compile(r"^(" + "|".join(re.escape(h) for h in SECTION_HEADERS.values()) + r"):[ \t]*$",
                       re.IGNORECASE | re.MULTILINE)

DROP = {"DISPO", "FAC", "DCI", "FU", "DXDC", "MEDDC"}     # design §3.5
# Written at or for discharge: any place word is masked. PR is always included: many templates (e.g. orthopaedics)
# put the course narrative and "discharged to rehab in stable condition" there even when an HC header exists
# (found in the step-3 independent review).
BROAD = {"HC", "COND", "PR"}


@dataclass(frozen=True)
class Section:
    code: str
    start: int
    end: int


def split_sections(text: str) -> list[Section]:
    out: list[Section] = []
    cur_code, cur_start = "HDR", 0
    for m in HEADER_RE.finditer(text):
        out.append(Section(cur_code, cur_start, m.start()))
        cur_code, cur_start = _BY_TEXT[m.group(1).lower()], m.end()
    out.append(Section(cur_code, cur_start, len(text)))
    return [s for s in out if text[s.start:s.end].strip()]


# ---------------------------------------------------------------- triggers (Hui Li + cfeng)
def _c(pattern: str) -> re.Pattern:
    """Notes are hard-wrapped: every literal space in a trigger matches any run of whitespace (cfeng's rule,
    origin/cfeng redact.py L83/L105; missing here was the main cause of the holes found in the step-3 review)."""
    return re.compile(pattern.replace("[- ]", r"[-\s]").replace(" ", r"\s+"), re.IGNORECASE)


PLACE_SNF = _c(
    r"\b(rehab\w*|snf|skilled nursing|nursing (home|facility)|extended care|ecf|long[- ]term care|ltc|ltach"
    r"|sub-?acute (rehab\w*|care|nursing|facility|snf|level)|facility|facilities|assisted living|alf"
    r"|inpatient rehab\w*|acute rehab\w*|irf|hospice)\b")
PLACE_HOME = _c(
    r"\b(home with\b|home health|vna|visiting nurse"
    r"|home (pt|ot|physical therapy|occupational therapy|services|safety evaluation|nursing|care)|services at home"
    r"|(with|elder) services|discharged? (to )?home|d/c(ed)? (to )?home|go(ing|es)? home|return(ed|ing|s)? (to )?home"
    r"|safe (for|to go) home|cleared (for|to go) home|home when|home once|outpatient (pt|physical therapy|rehab\w*)"
    r"|sen(t|d|ding) home|home (d/c|dc|discharge)|appropriate for home)\b"
    r"|___ services\b")
# Follow-up arrangements. In discharge-time sections any of these is masked; elsewhere only with plan context, so
# history such as "per PCP" or "seen by his PCP last week" survives in HPI.
# (?![a-z]) instead of \b where de-identified text glues tokens ("follow up At___ clinic").
FOLLOWUP = _c(
    r"\b(follow(ed)?[- ]?up(?![a-z])|f/u(?![a-z])|outpatient|as an outpatient|appointments?"
    r"|(with|see|call|contact|present to|seen by|until seen by|at) (her |his |their |your |the )?(pcp|primary care)\b"
    r"|pcp (to|should|will|for|appointment|visit)\b)")
DISPO_CONTEXT = _c(
    r"\b(dispo\w*|discharg\w* (to|with|home|back)|is (being )?discharged|ready for (discharge|d/c)"
    r"|discharge (plan\w*|planning)|d/c (to|plan\w*)|will (go|be going|return|be discharged)"
    r"|(will|would) (follow|f/u|see)|screen(ed|ing)|accepted (at|to|by)|bed (offer|availab\w*)|case manag\w*"
    r"|social work\w*|plan(ned|s)? (for|to)|recommend\w*|cleared (for|to))\b")
DISPO_STRONG = _c(
    r"\b(dispo(sition)?|screen(ed|ing) (for|by)|accepted (at|to|by)|bed (offer|availab\w*)|case manag\w*"
    r"|await(ing|ed)? (placement|bed|rehab\w*|snf)|(snf|rehab\w*|facility|nursing home|ltc|dispo\w*) placement"
    r"|placement (at|to|in) (a |an |the )?(snf|rehab\w*|facility|nursing|___)"
    r"|insurance (auth\w*|approval|denial)|discharge (teaching|instructions)|verbali[sz]ed (good )?understanding"
    r"|understanding (was )?verbali[sz]ed)\b")
# Self-care instructions given to the patient at discharge ("was instructed to complete / seek / call ...").
# Found by the step-3 text probe (feature "instructed to", mostly non-SNF). Only applied in discharge-time sections;
# "educated" / "taught" are left alone because patient teaching is skilled-care evidence (42 CFR 409.33(a)(3)).
# Discharge movement / arrangements in discharge-time sections: "discharged to ___", "discharged with home ___",
# "discharged with order for home hospital bed", "ready for discharge", "home" near "discharge" (step-3 review).
# A plain status at discharge ("At the time of discharge, he was ambulating") is kept: design §3.5 keeps
# Discharge Condition as the functional-status proxy.
DISCHARGE_MOVE = _c(
    r"\bdischarg\w* (on|to|with|home|back)\b|\bready for (discharge|d/c)\b|\bd/c(?:'?e?d)? (to|home|with|on)\b"
    r"|\bhome\b[^.;]{0,60}\bdischarg\w*|\bdischarg\w*[^.;]{0,60}\bhome\b"
    r"|\brecommend\w*[^.;]{0,30}\bhome\b|\b(continue|resume|recheck|monitor|contacted|check)\w*[^.;]{0,40}\bat home\b"
    r"|\b(on|upon|at|after) discharge,? (she|he|they|the patient|patient|pt) (will|should|is to|was to)\b")
DISCHARGE_SELF_CARE = _c(r"\b(was|were|is|are|been) (also )?instructed (to|not to|on)\b")
# Discharge-time sections only: post-discharge care arrangements. Found by hand-reviewing the wide-net hits after
# the step-3 review ("home O2 was arranged", "followed in the ___ clinic", "faxed to her PCP", "placement discussed
# with CM, SW", "hospital bed at home"). Medication history ("home dose", "home medications") does not match.
BROAD_PLAN = _c(
    # "placement" alone is clinical (PICC placement): only its disposition senses
    r"\b(pcp|primary care|clinic|outpatient|faxed|establish(ed)? care|arrang\w*|set up|cm|sw"
    r"|(options|need\w*|await\w*|pending|discussion|search|candidate) (for|of) placement"
    r"|placement (options|discussion|search|planning|process|issues)"
    r"|social work\w*|case manag\w*|hospital bed|visiting|services)\b"
    r"|\bhome (o2|oxygen|___|services|equipment|bed|nursing|health|pt|ot|care|infusion|iv|safety|visit\w*|hospice"
    r"|eval\w*)\b"
    r"|\bat home\b")
# Sub-headers inside the hospital course that start the post-discharge plan; everything after them is dropped.
PLAN_HEADER = _c(r"^\W*(transitional (issues?|care)|transitions? of care|discharge planning|issues for follow[- ]?up"
                 r"|follow[- ]?up (items|issues)|outstanding issues|pending (items|results)|to do)\b")
TODO_ITEM = re.compile(r"^\s*\[\s*[xX]?\s*\]")
# "therap(y|ies|ist)" only: "therap\w*" also matched "therapeutic" (INR therapeutic) and sent medication
# sentences down the clause-masking path.
THERAPY = re.compile(r"\b(pt|ot|slp|physical therap(y|ist)|occupational therap(y|ist)|speech( and swallow)?"
                     r"|therap(y|ies|ist|ists))\b", re.IGNORECASE)
CLAUSE_SPLIT = re.compile(r"(?<=[;,])\s+|\s+(?=\b(?:and|but|who|which)\b)|\s+-\s+", re.IGNORECASE)
SENT_SPLIT = re.compile(
    r"(?<!\b[A-Za-z]\.)(?<!\b(?:Dr|Mr|Ms|vs|St|no|No)\.)(?<!^\d\.)(?<!^\d\d\.)(?<=[.!?])\s+(?=[A-Z#\[(])")


@dataclass
class Span:
    span_id: str
    section: str
    start: int
    end: int
    text: str


def _logical_lines(text: str, start: int, end: int) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    pos = start
    for line in text[start:end].split("\n"):
        if out and out[-1][1].strip() and re.match(r"\s*[a-z]", line) and not out[-1][1].rstrip().endswith(":"):
            out[-1] = (out[-1][0], out[-1][1] + "\n" + line)
        else:
            out.append((pos, line))
        pos += len(line) + 1
    return out


def sentences(text: str, start: int, end: int) -> list[tuple[int, int]]:
    out = []
    for lstart, line in _logical_lines(text, start, end):
        if not line.strip():
            continue
        cuts = [0] + [m.end() for m in SENT_SPLIT.finditer(line)] + [len(line)]
        for a, b in pairwise(cuts):
            seg = line[a:b]
            if seg.strip():
                lead = len(seg) - len(seg.lstrip())
                out.append((lstart + a + lead, lstart + a + len(seg.rstrip())))
    return out


def _header_spans(text: str, sec: Section) -> list[Span]:
    """Header: keep the Service value and the Allergies block only (design §3.5, D-007)."""
    body = text[sec.start:sec.end]
    out = []
    m = re.search(r"(?m)^Service:[ \t]*(\S[^\n]*)$", body)
    if m:
        a, b = sec.start + m.start(), sec.start + m.end()
        out.append(Span("DS:HDR:SVC", "HDR", a, b, text[a:b].strip()))
    m = re.search(r"(?ms)^Allergies:[ \t]*(.*?)(?=^\s*Attending:|\Z)", body)
    if m and m.group(1).strip():
        a = sec.start + m.start()
        b = sec.start + m.end(1)
        out.append(Span("DS:HDR:ALG", "HDR", a, b, re.sub(r"\s+", " ", text[a:b]).strip()))
    return out


def index_note(text: str) -> list[Span]:
    """Every sentence of the original note with a stable span ID, before any redaction."""
    spans, seen = [], {}
    for sec in split_sections(text):
        if sec.code == "HDR":
            spans += _header_spans(text, sec)
            continue
        k = seen.get(sec.code, 0)
        seen[sec.code] = k + 1
        code = sec.code if k == 0 else f"{sec.code}{k + 1}"
        for i, (a, b) in enumerate(sentences(text, sec.start, sec.end), 1):
            spans.append(Span(f"DS:{code}:s{i}", sec.code, a, b, text[a:b]))
    return spans


def rule(sentence: str, section: str, broad: set[str] = BROAD) -> str | None:
    """Name of the rule marking this sentence as disposition leakage, or None (two-tier, Hui Li).
    Evaluated on the text as written and with "___" tokens blanked: MIMIC's de-identification tokens and our clause
    masks look the same, and a trigger may only match in one of the two forms."""
    return _rule(sentence, section, broad) or _rule(sentence.replace(MASK, " "), section, broad)


def _rule(sentence: str, section: str, broad: set[str]) -> str | None:
    snf, home, fu = PLACE_SNF.search(sentence), PLACE_HOME.search(sentence), FOLLOWUP.search(sentence)
    if section in broad:
        if snf:
            return "place_snf"
        if home:
            return "place_home"
        if fu:
            return "followup"
        if DISPO_STRONG.search(sentence):
            return "dispo_process"
        if DISCHARGE_MOVE.search(sentence):
            return "discharge_move"
        if DISCHARGE_SELF_CARE.search(sentence):
            return "discharge_self_care"
        if BROAD_PLAN.search(sentence):
            return "care_arrangement"
        if TODO_ITEM.search(sentence):
            return "todo_item"
        return None
    if (snf or home or fu) and DISPO_CONTEXT.search(sentence):
        return "place+plan"
    if DISPO_STRONG.search(sentence) and re.search(r"(?i)\bdischarg", sentence):
        return "dispo_process"
    return None


def _mask_clauses(sentence: str) -> str:
    parts = CLAUSE_SPLIT.split(sentence)
    seps = CLAUSE_SPLIT.findall(sentence)
    out = []
    for i, p in enumerate(parts):
        hit = (PLACE_SNF.search(p) or PLACE_HOME.search(p) or FOLLOWUP.search(p) or DISPO_STRONG.search(p)
               or DISCHARGE_MOVE.search(p) or DISCHARGE_SELF_CARE.search(p) or BROAD_PLAN.search(p))
        out.append(MASK if hit else p)
        if i < len(seps):
            out.append(seps[i])
    masked = "".join(out)
    return MASK if masked.replace(MASK, "").strip(" ,;.-") == "" else masked


def broad_sections(spans: list[Span]) -> set[str]:
    # PR is always broad now (Hui Li made it broad only when the note had no HC header).
    return set(BROAD)


# Independent wide net (NOT the redaction rules): any kept sentence where discharge / placement language and a
# place or home word co-occur, in any section. It over-flags on purpose (e.g. "recently discharged from rehab"
# in HPI is legitimate history); its hits are reviewed by hand, which is what makes it independent of rule().
WIDE_ACTION = _c(r"\b(discharg\w*|d/c|dispo\w*|placement|accepted|bed|transfer\w* to|going to|will go|"
                 r"plan(ned|s)? (for|to)|recommend\w*|arrang\w*|set up|follow[- ]?up)\b")
WIDE_PLACE = _c(r"\b(home|rehab\w*|snf|facility|facilities|nursing|hospice|vna|services|assisted|ltac\w*|"
                r"pcp|clinic|outpatient)\b|___")


def wide_net(spans: list[Span]) -> list[Span]:
    return [s for s in spans if WIDE_ACTION.search(s.text) and WIDE_PLACE.search(s.text.replace(MASK, " "))]


def redact(spans: list[Span]) -> tuple[list[Span], list[dict]]:
    """Kept spans (text possibly clause-masked) and a log of every removal."""
    broad = broad_sections(spans)
    kept, log = [], []
    plan_started: set[str] = set()      # section instances (e.g. "DS:HC") past a transitional-issues sub-header
    for s in spans:
        if s.section in DROP:
            log.append({"span_id": s.span_id, "section": s.section, "scope": "section", "rule": "drop_section"})
            continue
        inst = s.span_id.rsplit(":", 1)[0]
        if s.section in broad and (inst in plan_started or PLAN_HEADER.search(s.text)):
            plan_started.add(inst)
            log.append({"span_id": s.span_id, "section": s.section, "scope": "sentence", "rule": "transitional_issues"})
            continue
        text = s.text
        r = rule(text, s.section, broad)
        if r:
            if THERAPY.search(text):
                text = _mask_clauses(text)
                # a trigger can span clauses ("On discharge, she will ..."): if the masked sentence still fires a
                # rule, drop the whole sentence
                if text != MASK and rule(text, s.section, broad):
                    text = MASK
                scope = "sentence" if text == MASK else "clause"
            else:
                text, scope = MASK, "sentence"
            log.append({"span_id": s.span_id, "section": s.section, "scope": scope, "rule": r})
        if text != MASK:
            kept.append(Span(s.span_id, s.section, s.start, s.end, text))
    return kept, log


def residual(spans: list[Span], broad: set[str]) -> list[dict]:
    """Kept spans that still fire a leakage rule after redaction. This only proves the rules were applied
    consistently (clause masks, both "___" forms); it cannot find phrasings the rules do not know. The independent
    check is wide_net() plus hand review, then the 50-note human review (design §3.5)."""
    out = []
    for s in spans:
        r = rule(s.text, s.section, broad)
        if r:
            out.append({"span_id": s.span_id, "section": s.section, "rule": r})
    return out


def to_evidence(note_id: str, text: str) -> tuple[list[EvidenceItem], list[dict]]:
    spans = index_note(text)
    kept, log = redact(spans)
    ev = [EvidenceItem(ref_id=s.span_id, source=SOURCE_ID, kind="span", section=s.section, available_at=None,
                       text=s.text, provenance=f"discharge:note_id={note_id}:chars={s.start}-{s.end}")
          for s in kept]
    return ev, log
