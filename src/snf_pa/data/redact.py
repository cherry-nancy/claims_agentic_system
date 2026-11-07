"""Remove everything in a discharge note that could reveal the discharge disposition (deletion only).

Run from the project root:
    PYTHONPATH=src uv run python -m snf_pa.data.redact

Layers (the local-LLM span detector is added later as a third layer):
  1. Section allow-list. Template sections that state or assume the destination are dropped (Discharge Disposition,
     Facility, Followup Instructions, the letter in Discharge Instructions). Unknown text is dropped by default.
     The clinical sub-blocks of Discharge Instructions (weight bearing, wound care, anticoagulation, treatment
     frequency) are kept.
  2. Prescription dispensing details (RX lines, Disp, Refills): they say whether the patient fills prescriptions
     at a pharmacy, which differs sharply by destination, and carry no clinical facts the medication line lacks.
     As-needed (PRN) items of the discharge medication list go for the same reason (see MED_ITEM).
  3. Clause rules. A sentence with a disposition phrase loses only the clause that carries it, together with its
     connector ("..., and recommended for acute rehab"). A parenthetical with one is removed whole. A sentence left
     as a stub ("Patient was screened by.") is removed whole. Nothing is ever rewritten or inserted, and no marker is
     left where text was removed, since a count of markers would itself reveal the destination. For the same reason a
     numbered list that lost items is renumbered (1, 2, 4 -> 1, 2, 3); that is the one rewrite, and the only digits
     that change are list numbers.

Two modes:
  realistic - as above.
  strict    - also drops Discharge Medications: discharge prescriptions are written after the prior-auth request
              time (T_pa), so a reviewer would not have them (consensus plan).

Sentence IDs. Every sentence the model sees gets a packet ID, e.g. "DS:HC:s14" (14th sentence shown from the
Brief Hospital Course). IDs are numbered over the shown sentences only: numbering the original sentences would leave
gaps where text was removed, and the gaps would leak like markers do. The span table maps each ID back to its
character offsets in the original note, and also logs every removal (sentence, PRN item, dispensing detail,
dropped section) with its offsets and the rules that fired, so the redaction can be audited.

Writes data/sample/notes_redacted1{,_supp}.parquet (one row per note and mode) and the span tables
notes_redacted1{,_supp}_spans.parquet (gitignored). Prints aggregate counts only, never note text.
"""
import itertools
import re
from dataclasses import dataclass, field

import polars as pl

from snf_pa.data import config as C

VERSION = "rules-v3"
MODES = {"realistic": set(), "strict": {"Discharge Medications"}}  # mode -> extra sections dropped
FILES = {"notes_raw1": "notes_redacted1", "notes_raw1_supp": "notes_redacted1_supp"}

# MIMIC-IV-Note discharge template, in order. Headings are matched only in this order, so a heading repeated
# inside the text (e.g. "Past Medical History:" in the hospital course) stays part of the section it is in.
TEMPLATE = ["Name", "Admission Date", "Date of Birth", "Service", "Allergies", "Attending", "Chief Complaint",
            "Major Surgical or Invasive Procedure", "History of Present Illness", "Past Medical History",
            "Social History", "Family History", "Physical Exam", "Pertinent Results", "Brief Hospital Course",
            "Medications on Admission", "Discharge Medications", "Discharge Disposition", "Facility",
            "Discharge Diagnosis", "Discharge Condition", "Discharge Instructions", "Followup Instructions"]
KEEP = {"Service", "Allergies", "Chief Complaint", "Major Surgical or Invasive Procedure", "History of Present Illness",
        "Past Medical History", "Social History", "Family History", "Physical Exam", "Pertinent Results",
        "Brief Hospital Course", "Medications on Admission", "Discharge Medications", "Discharge Diagnosis",
        "Discharge Condition"}
# Clinical sub-blocks kept from Discharge Instructions (orthopaedic notes); the rest of that section is dropped.
INSTRUCTION_BLOCKS = ["Physical Therapy", "Treatments Frequency", "WOUND CARE", "ANTICOAGULATION",
                      "ACTIVITY AND WEIGHT BEARING"]
# Section code in packet IDs.
CODE = {"Sex": "SEX", "Service": "SVC", "Allergies": "ALG", "Chief Complaint": "CC",
        "Major Surgical or Invasive Procedure": "PROC", "History of Present Illness": "HPI",
        "Past Medical History": "PMH", "Social History": "SH", "Family History": "FH", "Physical Exam": "PE",
        "Pertinent Results": "RES", "Brief Hospital Course": "HC", "Medications on Admission": "MEDADM",
        "Discharge Medications": "MEDDC", "Discharge Diagnosis": "DX", "Discharge Condition": "COND",
        "Discharge Instructions/Physical Therapy": "DI-PT", "Discharge Instructions/Treatments Frequency": "DI-TX",
        "Discharge Instructions/WOUND CARE": "DI-WOUND", "Discharge Instructions/ANTICOAGULATION": "DI-ANTICOAG",
        "Discharge Instructions/ACTIVITY AND WEIGHT BEARING": "DI-ACT"}

HEADING = re.compile(r"(?m)^[ \t]*(" + "|".join(map(re.escape, TEMPLATE)) + r"):")
ANY_HEADING = re.compile(r"(?m)^[ \t]*[A-Z][A-Za-z ,/&\-]{2,45}:")
SEX = re.compile(r"Sex:[ \t]*\S+")

# As-needed items of the discharge medication list. A SNF list carries every PRN order nursing will give (bowel
# regimen, PR routes); a home list leaves most out, so the PRN items mark the destination (audit AUC of that
# section alone 0.74 -> 0.68 without them). Scheduled medications, injections and IV drugs stay.
MED_ITEM = re.compile(r"(?ms)^[ \t]*\d+\.[ \t].*?(?=^[ \t]*\d+\.[ \t]|\Z)")
PRN = re.compile(r"(?i)\bprn\b|as needed")

DISPENSING = re.compile(r"RX \*[^\n]*\n?|[ \t]*Disp:\*[^\n]*\n?|Disp #\*?[^\n]*?(?=Refills|\n|$)|Refills:\*?\d+")

# Disposition phrases, named for the report. Spaces match any whitespace (notes are hard-wrapped).
_DEST = (r"(?:(?:acute|inpatient|sub-?acute|short[- ]term|cardiac|pulmonary|pulm|physical)\s+)?rehab(?:ilitation)?"
         r"|\bSNF\b|skilled nursing|nursing (?:home|facility)|extended care|\bECF\b|\bLTACH?\b"
         r"|long[- ]term (?:acute )?care|\bfacility\b|\bfacilities\b|assisted living|\bhospice\b")
RULES = {
    "destination": _DEST,
    "home_services": r"home (?:with|w/) (?:services?|VNA|PT|OT|nursing)|\bVNA\b|visiting nurse"
                     r"|home (?:health|PT|OT|physical therapy|occupational therapy|services?|nursing|safety|care)",
    "movement": r"discharg\w*\s+(?:to|home|back)|\bd/?c(?:'?d|ed)?\s+(?:to|home)"
                r"|(?:go|going|sent|return\w*|went|back)\s+(?:back\s+)?(?:to\s+(?:his|her|their)\s+)?home",
    "plan_process": r"\bdispo(?:sition)?\b|(?:awaiting|pending|await|needs?|for|rehab|SNF|facility)\W+placement"
                    r"|bed (?:offer|availability|search|available)|\baccepted (?:at|to|by)\b|case manag\w*"
                    r"|insurance (?:auth\w*|approval|denial)|(?:safe|cleared|ready|stable) for (?:discharge|d/c|dc)\b"
                    # Discharge teaching boilerplate ("received discharge teaching and follow-up instructions with
                    # understanding verbalized and agreement with the discharge plan").
                    r"|discharge (?:teaching|instructions|plan)|follow[- ]?up instructions"
                    r"|verbali[sz]ed (?:good )?understanding|understanding (?:was )?verbali[sz]ed",
    # Follow-up arrangements are post-discharge plans and differ by destination ("PCP" as a source of history,
    # e.g. "per PCP", is kept).
    "followup": r"\boutpatient\b|(?:with|by|to|see|call|contact) (?:(?:her|his|their|your|the) )?PCP"
                r"|\bPCP (?:to|should|will|please|for)\b|\b(?:f/u|follow[- ]?up)(?: (?:with|in|at)\b|:)",
}
TRIGGERS = {k: re.compile(v.replace(" ", r"\s+"), re.IGNORECASE) for k, v in RULES.items()}

# A unit (bullet, numbered item, paragraph) ends at a blank line or at a line that starts a new item or heading.
UNIT_BREAK = re.compile(r"\n[ \t]*\n|\n(?=[ \t]*(?:[-*•#]|\d+[.)]\s|[A-Z][A-Za-z /&]{2,45}:))")
SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9#*(\-])")
CLAUSE_BREAK = re.compile(r",\s*|;\s*|:\s+|\s+-\s+|\s+(?:and|but|then|so|with plan for|plan for)\s+", re.IGNORECASE)
PAREN = re.compile(r"\s*\([^()]*\)")
# Marker of a list item ("4. ", "- "). It belongs to the item: shown with it, removed with it, never a sentence.
# The item's text may start on the next line ("1.\nFoo").
LIST_MARK = re.compile(r"[ \t]*(?:\d+[.)]|[-*\u2022])(?:[ \t]+|[ \t]*\n[ \t]*)")
ITEM_NUMBER = re.compile(r"(?m)^([ \t]*)(\d+)([.)])(?=\s)")
DANGLING = {"to", "for", "at", "with", "and", "or", "by", "of", "the", "a", "an", "his", "her", "their", "will",
            "be", "is", "was", "plan", "recommended", "recommends", "accepted", "screened", "pending", "awaiting"}


@dataclass
class Stats:
    sections_kept: list[str] = field(default_factory=list)
    dispensing: int = 0
    prn_items: int = 0
    parentheticals: int = 0
    clauses: int = 0
    sentences: int = 0
    rules: dict[str, int] = field(default_factory=lambda: dict.fromkeys(RULES, 0))
    # One row per sentence shown or removed, PRN item, dispensing detail and dropped section (see span()).
    spans: list[dict] = field(default_factory=list)

    def span(self, section: str, start: int, end: int, status: str, text: str = "", rules=()) -> None:
        """status: kept | trimmed (clauses removed) | removed | section_dropped | heading (of a shown section) |
        layout (a shown line with no text, e.g. "=====").
        Offsets index the original note."""
        self.spans.append({"section": section, "start": start, "end": end, "status": status, "text": text,
                           "rules": sorted(set(rules))})


def delete(text: str, idx: list[int], cuts: list[tuple[int, int]]) -> tuple[str, list[int]]:
    """Delete the (start, end) ranges of `text`; idx[i] is the original offset of text[i] and is carried along."""
    keep = [True] * len(text)
    for a, b in cuts:
        keep[a:b] = [False] * (b - a)
    return "".join(c for c, k in zip(text, keep) if k), [i for i, k in zip(idx, keep) if k]


def orig(idx: list[int], a: int, b: int) -> tuple[int, int]:
    """Original offsets of text[a:b] (a non-empty range)."""
    return idx[a], idx[b - 1] + 1

def triggers(s: str) -> list[tuple[int, int, str]]:
    return [(m.start(), m.end(), name) for name, rx in TRIGGERS.items() for m in rx.finditer(s)]


def sections(text: str) -> list[tuple[str, int, int]]:
    """(heading, start, end) for template headings found in template order."""
    found, last = [], -1
    for m in HEADING.finditer(text):
        i = TEMPLATE.index(m.group(1))
        if i > last:
            found.append((m.group(1), m.start()))
            last = i
    return [(h, s, found[k + 1][1] if k + 1 < len(found) else len(text)) for k, (h, s) in enumerate(found)]


def instruction_blocks(body: str) -> list[tuple[int, int]]:
    """(start, end) of the kept sub-blocks of Discharge Instructions, each from its heading to the next heading."""
    heads = list(ANY_HEADING.finditer(body))
    return [(m.start(), heads[k + 1].start() if k + 1 < len(heads) else len(body))
            for k, m in enumerate(heads) if m.group(0).strip().rstrip(":") in INSTRUCTION_BLOCKS]


def redact_sentence(s: str, st: Stats) -> str:
    """Remove the clauses of one sentence that carry a disposition phrase; '' if the sentence goes whole."""
    for m in reversed(list(PAREN.finditer(s))):
        if triggers(m.group(0)):
            s = s[:m.start()] + s[m.end():]
            st.parentheticals += 1
    hits = triggers(s)
    if not hits:
        return s
    for _, _, name in hits:
        st.rules[name] += 1
    # Alternating clause / delimiter spans over s.
    cuts = [(m.start(), m.end()) for m in CLAUSE_BREAK.finditer(s)]
    bounds = [0] + [x for c in cuts for x in c] + [len(s)]
    clauses = [(bounds[i], bounds[i + 1]) for i in range(0, len(bounds), 2)]
    hit = [any(s_ < b and e > a for s_, e, _ in hits) for a, b in clauses]
    # A fragment of under 3 words next to a removed clause ("Screened" in "Screened and accepted at ...") goes too.
    # A label ("Activity Status:") is not a fragment.
    hit = [h or ((k > 0 and hit[k - 1]) or (k + 1 < len(hit) and hit[k + 1]))
           and len(re.findall(r"[A-Za-z0-9]+", s[a:b])) < 3 and not (k < len(cuts) and s[cuts[k][0]] == ":")
           for k, (h, (a, b)) in enumerate(zip(hit, clauses))]
    if all(hit):
        st.sentences += 1
        return ""
    kept = [k for k, h in enumerate(hit) if not h]
    keep = [s[slice(*clauses[kept[0]])]]
    for prev, k in itertools.pairwise(kept):
        # Join with the delimiter that followed the previous kept clause (original order, so still deletion only).
        keep += [s[slice(*cuts[prev])], s[slice(*clauses[k])]]
    removed = len(clauses) - len(kept)
    st.clauses += removed
    out = re.sub(r"[\s,;:\-]+$", "", "".join(keep))
    tail = s[len(s.rstrip()):]  # trailing whitespace of the original sentence
    end = s.rstrip()[-1:] if s.rstrip()[-1:] in ".!?" and not out.endswith((".", "!", "?")) else ""
    words = re.findall(r"[A-Za-z0-9]+", out)
    if len(words) < 3 or words[-1].lower() in DANGLING:
        st.clauses -= removed
        st.sentences += 1
        return ""
    return out + end + tail


def redact_text(body: str, st: Stats, section: str, idx: list[int]) -> str:
    """Redact a section or block; its heading line is never touched. idx maps body offsets to the original note."""
    head = re.match(r"[ \t]*[^:\n]+:[ \t]*\n?", body)
    n_head = head.end() if head else 0
    if head:
        st.span(section, *orig(idx, len(head[0]) - len(head[0].lstrip()), len(head[0].rstrip())), "heading",
                head[0].strip())
    head, body, idx = body[:n_head], body[n_head:], idx[n_head:]
    cuts = [m.span() for m in DISPENSING.finditer(body) if m.end() > m.start()]
    st.dispensing += len(cuts)
    for a, b in cuts:
        st.span(section, *orig(idx, a, b), "removed", rules=["dispensing"])
    body, idx = delete(body, idx, cuts)
    out, pos = [], 0
    for ub in list(UNIT_BREAK.finditer(body)) + [None]:
        unit_end = ub.start() if ub else len(body)
        unit, sep = body[pos:unit_end], body[unit_end:ub.end()] if ub else ""
        mark = LIST_MARK.match(unit)
        m_end = mark.end() if mark else 0
        sents, layout, spos = [unit[:m_end]], [], m_end
        if mark:
            layout.append((pos + len(mark[0]) - len(mark[0].lstrip()), pos + len(mark[0].rstrip())))
        for sb in list(SENTENCE_BREAK.finditer(unit)) + [None]:
            send = sb.end() if sb else len(unit)
            sent = unit[spos:send]
            new = redact_sentence(sent, st)
            sents.append(new)
            a = pos + spos + len(sent) - len(sent.lstrip())
            b = pos + spos + len(sent.rstrip())
            if re.search(r"[A-Za-z0-9]", sent):
                whole = new == sent and idx[b - 1] - idx[a] == b - 1 - a  # nothing cut inside, dispensing included
                status = "kept" if whole else "trimmed" if new.strip() else "removed"
                st.span(section, *orig(idx, a, b), status, new.strip(), [n for *_, n in triggers(sent)])
            elif sent.strip():  # rules ("====="), blanks ("___"), lone bullets: shown only with their unit
                layout.append((a, b))
            spos = send
        new = "".join(sents)
        shown = bool(re.search(r"[A-Za-z0-9]", new[m_end:]))
        for a, b in layout:
            st.span(section, *orig(idx, a, b), "layout" if shown else "removed", body[a:b] if shown else "")
        if shown or not unit.strip():
            out += [new, sep]  # a unit removed whole takes its line break with it
        pos = ub.end() if ub else len(body)
    return head + "".join(out)


def renumber(text: str) -> str:
    """Number the items of each list 1, 2, 3 ... A list restarts where the original numbering does not increase."""
    last, k = 0, 0

    def number(m: re.Match) -> str:
        nonlocal last, k
        n = int(m[2])
        k = 1 if n <= last else k + 1
        last = n
        return f"{m[1]}{k}{m[3]}"
    return ITEM_NUMBER.sub(number, text)


def tidy(text: str) -> str:
    """Deletion-only cleanup: blank bullets, spaces before punctuation, runs of blank lines."""
    text = re.sub(r"(?m)^[ \t]*[-*•#][ \t]*$\n?", "", text)
    text = re.sub(r"[ \t]+(?=[,.;:])", "", text)
    return re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", text).strip()


def redact(text: str, mode: str = "realistic") -> tuple[str, Stats]:
    st, parts = Stats(), []
    drop = MODES[mode]
    for heading, a, b in sections(text):
        body, idx = text[a:b], list(range(a, b))
        if heading == "Date of Birth" and (m := SEX.search(body)):
            parts.append(("Sex", body[m.start():m.end() + 1]))  # "Sex: F" and its line break
            st.span(heading, a, b, "section_dropped")  # the rest of the line
            st.span("Sex", a + m.start(), a + m.end(), "kept", m.group(0))
        elif heading in KEEP and heading not in drop:
            if heading == "Discharge Medications":
                cuts = [m.span() for m in MED_ITEM.finditer(body) if PRN.search(m.group(0))]
                st.prn_items += len(cuts)
                for c in cuts:
                    st.span(heading, *orig(idx, *c), "removed", rules=["prn"])
                body, idx = delete(body, idx, cuts)
            parts.append((heading, redact_text(body, st, heading, idx)))
        elif heading == "Discharge Instructions":
            for i, j in instruction_blocks(body):
                name = "Discharge Instructions/" + body[i:j].split(":")[0].strip()
                parts.append((name, redact_text(body[i:j], st, name, idx[i:j])))
            st.span(heading, a, b, "section_dropped")  # the rest of it (the kept blocks are also logged)
        else:
            st.span(heading, a, b, "section_dropped")
    # A section or block with nothing left under its heading is dropped, heading included.
    shown = {h for h, p in parts if h == "Sex" or re.search(r"[A-Za-z0-9]", p.split(":", 1)[1])}
    parts = [(h, renumber(p)) for h, p in parts if h in shown]
    for sp in st.spans:
        if sp["status"] == "heading" and sp["section"] not in shown:
            sp["status"] = "removed"
    st.sections_kept = [h for h, _ in parts if h != "Sex"]
    # Packet IDs, numbered over the sentences shown, per section.
    n = dict.fromkeys(CODE, 0)
    for sp in st.spans:
        sp["packet_id"] = None
        if sp["status"] in ("kept", "trimmed") and sp["section"] in shown:
            n[sp["section"]] += 1
            sp["packet_id"] = f"DS:{CODE[sp['section']]}:s{n[sp['section']]}"
    return tidy("".join(p for _, p in parts)), st


def is_deletion_of(out: str, original: str) -> bool:
    """True if `out` can be made from `original` by deleting characters only."""
    it = iter(original)
    return all(ch in it for ch in out)


def is_redaction_of(out: str, original: str) -> bool:
    """True if `out` can be made from `original` by deleting characters and renumbering list items."""
    def mask(s: str) -> str:
        return ITEM_NUMBER.sub(r"\1#\3", s)
    return is_deletion_of(mask(out), mask(original))


def check_spans(spans: list[dict], original: str) -> None:
    """Every span points at the text it claims: shown text is the original sentence or a deletion of it."""
    for sp in spans:
        src = original[sp["start"]:sp["end"]]
        assert src.strip(), sp
        assert sp["status"] != "kept" or sp["text"] == src, sp["packet_id"]
        assert is_deletion_of(sp["text"], src), sp["packet_id"]


def main() -> None:
    key = ["hadm_id", "discharge_location"]
    cases = pl.concat([pl.read_csv(C.SAMPLE_DIR / f"{f}.csv", infer_schema_length=0).select(key)
                       for f in ["sample_cases1", "sample_cases1_supp"]])
    reports = []
    for src, dst in FILES.items():
        notes = pl.read_parquet(C.SAMPLE_DIR / f"{src}.parquet")
        rows, spans = [], []
        for r in notes.iter_rows(named=True):
            for mode in MODES:
                out, st = redact(r["text"], mode)
                assert is_redaction_of(out, r["text"]), "redaction must only delete (and renumber lists)"
                check_spans(st.spans, r["text"])
                rows.append({"note_id": r["note_id"], "subject_id": r["subject_id"], "hadm_id": r["hadm_id"],
                             "mode": mode, "text": out, "redaction_version": VERSION,
                             "sections_kept": st.sections_kept,
                             "has_hospital_course": "Brief Hospital Course" in st.sections_kept,
                             "n_dispensing": st.dispensing, "n_prn_items": st.prn_items,
                             "n_parentheticals": st.parentheticals, "n_clauses_removed": st.clauses,
                             "n_sentences_removed": st.sentences, "chars_in": len(r["text"]), "chars_out": len(out),
                             **{f"rule_{k}": v for k, v in st.rules.items()}})
                spans += [{"note_id": r["note_id"], "mode": mode, "redaction_version": VERSION, **sp}
                          for sp in st.spans]
        df = pl.DataFrame(rows)
        df.write_parquet(C.SAMPLE_DIR / f"{dst}.parquet")
        pl.DataFrame(spans).write_parquet(C.SAMPLE_DIR / f"{dst}_spans.parquet")
        reports.append(df.drop("text", "sections_kept"))
    rep = pl.concat(reports).with_columns(pl.col("hadm_id").cast(pl.String)).join(cases, on="hadm_id")
    print(f"redacted {rep.height // len(MODES)} notes x {len(MODES)} modes ({VERSION})")
    with pl.Config(tbl_width_chars=200, tbl_cols=20, tbl_rows=20):
        print(rep.group_by("mode", "discharge_location").agg(
            pl.len().alias("n"), (pl.col("chars_out") / pl.col("chars_in")).median().round(2).alias("kept_frac"),
            pl.col("has_hospital_course").mean().round(2).alias("has_HC"),
            pl.col("n_dispensing").mean().round(1), pl.col("n_prn_items").mean().round(1),
            pl.col("n_clauses_removed").mean().round(1), pl.col("n_sentences_removed").mean().round(1),
            pl.col("n_parentheticals").mean().round(1),
            *[pl.col(f"rule_{k}").mean().round(1) for k in RULES]).sort("mode", "discharge_location"))


if __name__ == "__main__":
    main()
