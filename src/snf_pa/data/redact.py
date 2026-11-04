"""Step 2: remove discharge-disposition leakage and index sentences with stable span IDs.

Two packets are built from the same spans (plan D7/D8):
  strict     main experiment; PT/OT disposition recommendations masked, discharge meds dropped
  realistic  ablation; PT/OT recommendations kept, discharge meds kept with Rx/Disp/Refills removed
Span IDs (D9) look like 'DS:HC:s14' and are identical in both packets.
"""
import re
from dataclasses import dataclass
from itertools import pairwise

from .sections import split_sections

MASK = "[REDACTED-DISPO]"

# Sections dropped whole. MEDDC is kept (cleaned) in the realistic packet only.
DROP_ALWAYS = {"DISPO", "FAC", "DXDC", "DCI", "FU"}
DROP_STRICT_ONLY = {"MEDDC"}
# Sections written during or for discharge: any place word is masked.
BROAD = {"HC", "COND", "MEDDC"}
# Everything else describes the patient before or at admission (e.g. 'lives in a nursing home'
# is legitimate C6 evidence), so only sentences that also talk about the discharge plan are masked.

# 'placement' and 'subacute' alone are usually clinical (PICC placement, subacute infarct), so they
# only count in disposition phrases.
PLACE_SNF = re.compile(
    r"\b(rehab\w*|snf|skilled nursing|nursing (home|facility)|extended care|ecf|long[- ]term care|ltc|ltach"
    r"|sub-?acute (rehab\w*|care|nursing|facility|snf|level)|facility|facilities|assisted living|alf"
    r"|inpatient rehab\w*|acute rehab\w*|irf)\b",
    re.IGNORECASE,
)
PLACE_HOME = re.compile(
    r"\b(home with\b|home health|vna|visiting nurse"
    r"|home (pt|ot|physical therapy|occupational therapy|services|safety evaluation)|services at home"
    r"|(with|elder) services|discharged? (to )?home|d/c(ed)? (to )?home|go(ing|es)? home|return(ed|ing|s)? (to )?home"
    r"|safe (for|to go) home|cleared (for|to go) home|home when|home once|outpatient (pt|physical therapy|rehab\w*))\b"
    r"|___ services\b",
    re.IGNORECASE,
)
# Talk about the current discharge plan (not past history such as 'was discharged from rehab in May').
DISPO_CONTEXT = re.compile(
    r"\b(dispo\w*|discharge (to|plan\w*|planning|home)|d/c (to|plan\w*)|will (go|be going|return|be discharged)"
    r"|screen(ed|ing)|accepted (at|to|by)|bed (offer|availab\w*)|case manag\w*|social work\w*"
    r"|plan(ned|s)? (for|to)|recommend\w*|cleared (for|to))\b",
    re.IGNORECASE,
)
# Screening / acceptance language reveals placement even without a place word.
DISPO_STRONG = re.compile(
    r"\b(dispo(sition)?|screen(ed|ing) (for|by)|accepted (at|to|by)|bed (offer|availab\w*)|case manag\w*"
    r"|await(ing|ed)? (placement|bed|rehab\w*|snf)|(snf|rehab\w*|facility|nursing home|ltc|dispo\w*) placement"
    r"|placement (at|to|in) (a |an |the )?(snf|rehab\w*|facility|nursing|___))\b",
    re.IGNORECASE,
)
THERAPY = re.compile(r"\b(pt|ot|slp|physical therap\w*|occupational therap\w*|speech( and swallow)?|therap\w*)\b",
                     re.IGNORECASE)
CLAUSE_SPLIT = re.compile(r"(?<=[;,])\s+|\s+(?=\b(?:and|but|who|which)\b)|\s+-\s+", re.IGNORECASE)
# Sentence end followed by a capital; not after single-letter abbreviations (p.o.), titles, or list numbers.
SENT_SPLIT = re.compile(
    r"(?<!\b[A-Za-z]\.)(?<!\b(?:Dr|Mr|Ms|vs|St|no|No)\.)(?<!^\d\.)(?<!^\d\d\.)(?<=[.!?])\s+(?=[A-Z#\[(])"
)
RX_LINE = re.compile(r"(?im)^\s*RX\s.*$")
DISP_TAIL = re.compile(r"(?i)\s*Disp\s*#.*?(Refills?:?\s*\*?\d+)?\s*$", re.MULTILINE)


@dataclass
class Span:
    span_id: str
    section: str
    start: int
    end: int
    text: str


def _logical_lines(text: str, start: int, end: int) -> list[tuple[int, str]]:
    """Lines of text[start:end] with wrapped continuations (next line starts lowercase) joined back on."""
    out: list[tuple[int, str]] = []
    pos = start
    for line in text[start:end].split("\n"):
        if out and out[-1][1].strip() and re.match(r"\s*[a-z]", line) and not out[-1][1].rstrip().endswith(":"):
            out[-1] = (out[-1][0], out[-1][1] + "\n" + line)
        else:
            out.append((pos, line))
        pos += len(line) + 1
    return out


def sentences(text: str, sec_start: int, sec_end: int) -> list[tuple[int, int]]:
    """Character ranges of sentences in text[sec_start:sec_end]: split on lines, then on sentence ends."""
    out = []
    for lstart, line in _logical_lines(text, sec_start, sec_end):
        if not line.strip():
            continue
        cuts = [0] + [m.end() for m in SENT_SPLIT.finditer(line)] + [len(line)]
        for a, b in pairwise(cuts):
            seg = line[a:b]
            if seg.strip():
                lead = len(seg) - len(seg.lstrip())
                out.append((lstart + a + lead, lstart + a + len(seg.rstrip())))
    return out


def index_note(text: str) -> list[Span]:
    """All sentences of the note with span IDs, before any redaction."""
    spans, seen = [], {}
    for sec in split_sections(text):
        k = seen.get(sec.code, 0)
        seen[sec.code] = k + 1
        code = sec.code if k == 0 else f"{sec.code}{k + 1}"
        for i, (a, b) in enumerate(sentences(text, sec.start, sec.end), 1):
            spans.append(Span(f"DS:{code}:s{i}", sec.code, a, b, text[a:b]))
    return spans


def _rule(sentence: str, section: str, broad: set[str] = BROAD) -> str | None:
    """Name of the rule that marks this sentence as disposition leakage, or None."""
    snf, home = PLACE_SNF.search(sentence), PLACE_HOME.search(sentence)
    if section in broad:
        if snf:
            return "place_snf"
        if home:
            return "place_home"
        if DISPO_STRONG.search(sentence):
            return "dispo_process"
        return None
    if (snf or home) and DISPO_CONTEXT.search(sentence):
        return "place_snf+plan" if snf else "place_home+plan"
    if DISPO_STRONG.search(sentence) and re.search(r"(?i)\bdischarg", sentence):
        return "dispo_process"
    return None


def _mask_clauses(sentence: str) -> str:
    """Mask only the clauses that carry the recommendation; keep functional descriptions."""
    parts = CLAUSE_SPLIT.split(sentence)
    seps = CLAUSE_SPLIT.findall(sentence)
    out = []
    for i, p in enumerate(parts):
        hit = PLACE_SNF.search(p) or PLACE_HOME.search(p) or DISPO_STRONG.search(p)
        out.append(MASK if hit else p)
        if i < len(seps):
            out.append(seps[i])
    masked = "".join(out)
    return MASK if masked.replace(MASK, "").strip(" ,;.-") == "" else masked


def clean_discharge_meds(sentence: str) -> str:
    """Realistic packet: keep drug, dose, route, frequency; drop Rx/Disp/Refills prescription details."""
    s = RX_LINE.sub("", sentence)
    return DISP_TAIL.sub("", s).strip()


def redact(spans: list[Span], packet: str) -> tuple[list[Span], list[dict]]:
    """Apply the packet's rules. Returns kept spans and a log of changes.

    Sentences masked whole are left out of the packet (a visible marker would itself hint at the label);
    clause-level masks inside PT/OT sentences keep the MASK marker so the sentence still reads.
    """
    assert packet in ("strict", "realistic")
    drop = DROP_ALWAYS | (DROP_STRICT_ONLY if packet == "strict" else set())
    # Without a Brief Hospital Course header the course text sits in Pertinent Results.
    broad = BROAD | ({"PR"} if not any(s.section == "HC" for s in spans) else set())
    kept, log = [], []
    for s in spans:
        if s.section in drop:
            log.append({"span_id": s.span_id, "section": s.section, "scope": "section", "rule": "drop_section"})
            continue
        text = clean_discharge_meds(s.text) if s.section == "MEDDC" else s.text
        if not text:
            log.append({"span_id": s.span_id, "section": s.section, "scope": "sentence", "rule": "rx_line"})
            continue
        rule = _rule(text, s.section, broad)
        if rule:
            therapy = THERAPY.search(text)
            if therapy and packet == "realistic":
                rule = None  # D8: realistic packet keeps PT/OT recommendations
            elif therapy:
                text = _mask_clauses(text)
                scope = "sentence" if text == MASK else "clause"
                log.append({"span_id": s.span_id, "section": s.section, "scope": scope, "rule": "therapy_" + rule})
            else:
                log.append({"span_id": s.span_id, "section": s.section, "scope": "sentence", "rule": rule})
                text = MASK
        if text != MASK:
            kept.append(Span(s.span_id, s.section, s.start, s.end, text))
    return kept, log
