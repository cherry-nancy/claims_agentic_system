"""Disposition redaction on synthetic notes (no MIMIC text here)."""
import re

from snf_pa.data.redact import (
    MODES,
    Stats,
    check_spans,
    is_deletion_of,
    is_redaction_of,
    redact,
    redact_sentence,
)

NOTE = """Name: ___  Unit No: ___

Admission Date: ___  Discharge Date: ___

Date of Birth: ___  Sex: F

Service: ORTHOPAEDICS

Allergies:
Penicillins

Attending: ___.

Chief Complaint:
right hip pain

History of Present Illness:
Ms. ___ is an ___ woman who fell at home and was found to have a
right femoral neck fracture. Per PCP, she has mild dementia.

Brief Hospital Course:
Patient underwent right hemiarthroplasty. Seen by PT; ambulated 20 ft
with rolling walker, mod assist x2, and recommended for acute rehab.
Screened and accepted at facility, will need daily wound care for
sacral ulcer. Pain controlled on oxycodone (dispo to rehab pending bed).

TRANSITIONAL ISSUES:
- Dispo: home with VNA
- Lovenox 40 mg SC daily x 4 weeks
- Recheck BMP in 1 week, follow up with PCP.
- Patient will be discharged to rehab.

Discharge Medications:
1. Enoxaparin Sodium 40 mg SC DAILY
RX *enoxaparin 40 mg/0.4 mL 40 mg SC daily Disp #*28 Syringe Refills:*0
2. Acetaminophen 650 mg PO Q6H
3. Senna 8.6 mg PO BID
Disp:*60 Tablet(s)* Refills:*2*
4. Bisacodyl 10 mg PR DAILY:PRN constipation

Discharge Disposition:
Extended Care

Facility:
___

Discharge Diagnosis:
right femoral neck fracture

Discharge Condition:
Mental Status: Clear and coherent.
Activity Status: Out of Bed with assistance to chair or wheelchair.

Discharge Instructions:
Dear Ms. ___, you are being discharged to rehab.

Physical Therapy:
WBAT RLE
Treatments Frequency:
Daily dry dressing change; staples out at rehab in 2 weeks.

Followup Instructions:
___
"""


def test_removes_every_disposition_clue():
    out, _ = redact(NOTE)
    low = out.lower()
    for clue in ["rehab", "facility", "extended care", "vna", "dispo", "discharged to", "accepted", "refills",
                 "disp", "rx *", "dear", "followup", "screened", "follow up", "with pcp", "bisacodyl"]:
        assert clue not in low, clue


def test_keeps_clinical_facts_in_the_same_sentences():
    out, _ = redact(NOTE)
    for fact in ["ambulated 20 ft", "mod assist x2", "daily wound care", "sacral ulcer", "Pain controlled on oxycodone",
                 "Lovenox 40 mg SC daily x 4 weeks", "Enoxaparin Sodium 40 mg SC DAILY", "WBAT RLE",
                 "Daily dry dressing change", "Out of Bed with assistance", "fell at home", "Sex: F",
                 "Penicillins", "ORTHOPAEDICS", "Discharge Condition:", "TRANSITIONAL ISSUES:\n- Lovenox",
                 "will need daily wound care", "SC DAILY\n2. Acetaminophen", "Senna 8.6 mg PO BID",
                 "Recheck BMP in 1 week", "Per PCP, she has mild dementia"]:
        assert fact in out, fact


def test_deletion_only():
    out, _ = redact(NOTE)
    assert is_redaction_of(out, NOTE)


def test_clause_not_sentence():
    st = Stats()
    s = "Seen by PT, ambulated 20 ft with rolling walker, and recommended for acute rehab."
    assert redact_sentence(s, st) == "Seen by PT, ambulated 20 ft with rolling walker."
    assert st.clauses == 1 and st.sentences == 0


def test_stub_sentence_goes_whole():
    st = Stats()
    assert redact_sentence("Patient was screened by rehab.", st) == ""
    assert st.sentences == 1


def test_clinical_uses_of_trigger_words_are_kept():
    st = Stats()
    for s in ["PICC line placement was confirmed by CXR.", "Takes her home medications as prescribed.",
              "On 2L home O2 at baseline.", "Transferred to the ICU for hypotension."]:
        assert redact_sentence(s, st) == s, s


def test_strict_mode_drops_discharge_medications_only():
    realistic, _ = redact(NOTE, "realistic")
    strict, st = redact(NOTE, "strict")
    assert "Discharge Medications:" in realistic and "Discharge Medications:" not in strict
    assert "Discharge Medications" not in st.sections_kept
    assert "Lovenox 40 mg SC daily x 4 weeks" in strict and is_redaction_of(strict, NOTE)


def test_spans_point_at_the_original_note():
    for mode in MODES:
        _, st = redact(NOTE, mode)
        check_spans(st.spans, NOTE)
        for sp in st.spans:
            if sp["status"] == "kept":
                assert NOTE[sp["start"]:sp["end"]] == sp["text"]


def test_packet_ids_have_no_gaps_and_cover_the_shown_text():
    out, st = redact(NOTE)
    shown = [sp for sp in st.spans if sp["packet_id"]]
    by_section = {}
    for sp in shown:
        by_section.setdefault(sp["packet_id"].rsplit(":", 1)[0], []).append(int(sp["packet_id"].rsplit("s", 1)[1]))
    assert all(n == list(range(1, len(n) + 1)) for n in by_section.values()), by_section
    assert all(sp["status"] in ("removed", "section_dropped", "heading", "layout") for sp in st.spans if not sp["packet_id"])
    norm = re.sub(r"\s+", "", out)
    assert all(re.sub(r"\s+", "", sp["text"]) in norm for sp in shown)


def test_removals_are_logged_with_their_rules():
    _, st = redact(NOTE)
    hc = [sp for sp in st.spans if sp["section"] == "Brief Hospital Course"]
    assert [sp["packet_id"] for sp in hc if sp["status"] == "trimmed"][:1] == ["DS:HC:s2"]
    assert any(sp["status"] == "removed" and "movement" in sp["rules"] for sp in st.spans)
    assert sum("prn" in sp["rules"] for sp in st.spans) == 1
    assert sum("dispensing" in sp["rules"] for sp in st.spans) == st.dispensing > 0
    dropped = {sp["section"] for sp in st.spans if sp["status"] == "section_dropped"}
    assert {"Discharge Disposition", "Facility", "Followup Instructions", "Discharge Instructions"} <= dropped


def test_review_marks_every_removal_and_nothing_shown():
    import html

    from snf_pa.data.review import marked
    for mode in MODES:
        out, st = redact(NOTE, mode)
        page = marked(NOTE, st.spans)
        assert html.unescape(re.sub(r"<[^>]+>", "", page)) == NOTE  # the whole original, in order
        unmarked = html.unescape(re.sub(r'<span class="(cut|drop)">[^<]*</span>', "", page))
        def flat(s):
            return re.sub(r"\s+", "", re.sub(r"(?m)^([ \t]*)\d+([.)])", r"\1#\2", s))
        assert flat(out) == flat(unmarked), mode  # shown = unmarked text, list numbers aside
        assert '<span class="cut">' in page and '<span class="drop">' in page
        assert "recommended for acute rehab" not in unmarked and "Extended Care" not in unmarked


LIST = """Brief Hospital Course:
Admitted for atrial fibrillation with RVR, rate controlled on metoprolol.

TRANSITIONAL ISSUES:
1. Follow up with PCP in 1 week.
2. Patient will be discharged to rehab.
3. Recheck potassium in 3 days.
4. Continued counseling regarding alcohol use.
5. Ambulatory cardiac monitoring for atrial fibrillation.
"""


def test_list_items_go_whole_and_the_rest_is_renumbered():
    out, st = redact(LIST)
    items = re.findall(r"(?m)^(\d+)\. (.*)$", out)
    assert [n for n, _ in items] == ["1", "2", "3"]
    assert [x for _, x in items] == ["Recheck potassium in 3 days.", "Continued counseling regarding alcohol use.",
                                     "Ambulatory cardiac monitoring for atrial fibrillation."]
    assert not re.search(r"(?m)^\s*\d+\.\s*$", out)  # no empty items
    assert is_redaction_of(out, LIST) and not is_deletion_of(out, LIST)
    check_spans(st.spans, LIST)
    assert all(not re.match(r"\d+\.", sp["text"]) for sp in st.spans if sp["packet_id"])  # markers are not sentences


def test_a_new_list_restarts_numbering():
    from snf_pa.data.redact import renumber
    assert renumber("1. a\n3. b\n1. c\n4. d\n") == "1. a\n2. b\n1. c\n2. d\n"


def test_an_item_whose_text_starts_on_the_next_line_goes_with_its_number():
    out, _ = redact("Brief Hospital Course:\nTreated for pneumonia with ceftriaxone.\n\nTRANSITIONAL ISSUES:\n"
                    "1.\nPatient will be discharged to rehab.\n2.\nRepeat chest x-ray in 6 weeks.\n")
    assert "1.\nRepeat chest x-ray in 6 weeks." in out and "2." not in out


def test_discharge_teaching_boilerplate_goes_and_the_clinical_status_stays():
    st = Stats()
    status = "On the day of discharge she was afebrile, walking, with a foley in place, and pain was controlled."
    teaching = "She was given discharge teaching and follow-up instructions with understanding verbalized."
    assert redact_sentence(status, st) == status
    assert redact_sentence(teaching, st) == ""
    assert redact_sentence("Discharge plan reviewed with her daughter, who agrees.", st) == ""
