"""Step 2 unit tests on a synthetic discharge summary (no MIMIC data)."""
from snf_pa.data.redact import MASK, clean_discharge_meds, index_note, redact, sentences
from snf_pa.data.sections import split_sections

NOTE = """Name:  ___                     Unit No:   ___
Service: ORTHOPAEDICS

Chief Complaint:
Right hip pain after fall

History of Present Illness:
Mr. ___ is an ___ yo man who fell at home. He was recently discharged from rehab in ___.

Social History:
Lives alone in a second-floor apartment. Daughter visits weekly.

Pertinent Results:
CT head: subacute infarct in the left frontal lobe.

Brief Hospital Course:
Patient underwent ORIF on POD0. Pain was controlled with p.o. oxycodone.
A PICC line placement was done for IV antibiotics.
PT evaluated him and found he needs moderate assist for transfers, and recommended discharge to rehab.
Case management screened for SNF placement.
He was started on home medications on POD1.
TRANSITIONAL ISSUES:
- VNA to draw INR on ___

Medications on Admission:
1. Lisinopril 10 mg PO DAILY

Discharge Medications:
1. Oxycodone 5 mg PO Q4H:PRN pain
RX *oxycodone 5 mg 1 tablet(s) by mouth every four hours Disp #*20 Tablet Refills:*0

Discharge Disposition:
Extended Care

Facility:
___

Discharge Diagnosis:
Right femoral neck fracture

Discharge Condition:
Mental Status: Clear and coherent.
Activity Status: Out of Bed with assistance to chair or wheelchair.

Discharge Instructions:
You were admitted after a fall.

Followup Instructions:
___
"""


def texts(spans):
    return " ".join(s.text for s in spans)


def test_sections_found_in_order():
    codes = [s.code for s in split_sections(NOTE)]
    assert codes == ["HDR", "CC", "HPI", "SH", "PR", "HC", "MEDADM", "MEDDC", "DISPO", "FAC", "DXDC", "COND",
                     "DCI", "FU"]


def test_sentence_split_keeps_abbreviations():
    spans = index_note(NOTE)
    hc = [s.text for s in spans if s.section == "HC"]
    assert hc[0] == "Patient underwent ORIF on POD0."
    assert hc[1] == "Pain was controlled with p.o. oxycodone."


def test_span_offsets_point_into_original():
    for s in index_note(NOTE):
        assert NOTE[s.start:s.end] == s.text


def test_strict_drops_sections_and_masks_disposition():
    kept, log = redact(index_note(NOTE), "strict")
    out = texts(kept)
    for gone in ("Extended Care", "You were admitted after a fall", "Right femoral neck fracture", "Oxycodone 5 mg PO"):
        assert gone not in out
    assert "screened for SNF" not in out and "VNA" not in out
    # PT sentence: recommendation masked, function kept
    pt = next(s.text for s in kept if s.text.startswith("PT evaluated"))
    assert "moderate assist for transfers" in pt and "rehab" not in pt and MASK in pt
    assert {x["rule"] for x in log if x["scope"] == "section"} == {"drop_section"}


def test_pre_admission_history_is_kept():
    kept, _ = redact(index_note(NOTE), "strict")
    out = texts(kept)
    assert "Lives alone in a second-floor apartment." in out
    assert "recently discharged from rehab" in out  # history, not the current discharge plan
    assert "He was started on home medications on POD1." in out  # 'home medications' is not a disposition
    assert "Activity Status: Out of Bed with assistance to chair or wheelchair." in out


def test_clinical_uses_of_disposition_words_are_kept():
    kept, _ = redact(index_note(NOTE), "strict")
    out = texts(kept)
    assert "A PICC line placement was done for IV antibiotics." in out
    assert "CT head: subacute infarct in the left frontal lobe." in out


def test_whole_sentence_masks_are_omitted():
    kept, log = redact(index_note(NOTE), "strict")
    masked_whole = {x["span_id"] for x in log if x["scope"] == "sentence"}
    assert masked_whole and not masked_whole & {s.span_id for s in kept}
    assert all(s.text != MASK for s in kept)


def test_pertinent_results_is_broad_when_course_header_missing():
    note = "Pertinent Results:\nWBC 9.\nHe was screened and will go to rehab.\n\nDischarge Condition:\nStable.\n"
    kept, _ = redact(index_note(note), "strict")
    assert "rehab" not in texts(kept) and "WBC 9." in texts(kept)
    with_hc = note.replace("Discharge Condition:", "Brief Hospital Course:\nUneventful.\n\nDischarge Condition:")
    with_hc = with_hc.replace("He was screened and will go to rehab.", "Prior stay at rehab in ___.")
    kept, _ = redact(index_note(with_hc), "strict")
    assert "Prior stay at rehab" in texts(kept)  # narrow rules: no discharge-plan language


def test_realistic_keeps_pt_recommendation_and_clean_meds():
    kept, _ = redact(index_note(NOTE), "realistic")
    out = texts(kept)
    assert "recommended discharge to rehab" in out
    assert "Oxycodone 5 mg PO Q4H:PRN pain" in out
    assert "Disp" not in out and "RX " not in out
    assert "screened for SNF" not in out  # non-therapy disposition still masked


def test_span_ids_stable_across_packets():
    spans = index_note(NOTE)
    strict = {s.span_id for s in redact(spans, "strict")[0]}
    realistic = {s.span_id for s in redact(spans, "realistic")[0]}
    assert strict <= realistic
    assert all(i.startswith("DS:MEDDC:") for i in realistic - strict)


def test_clean_discharge_meds():
    assert clean_discharge_meds("RX *aspirin 81 mg daily Disp #*30 Tablet Refills:*0") == ""
    assert clean_discharge_meds("1. Aspirin 81 mg PO DAILY") == "1. Aspirin 81 mg PO DAILY"


def test_wrapped_sentence_is_masked_whole():
    note = "Brief Hospital Course:\nShe is being discharged home with services in stable\ncondition.\nNext item.\n"
    kept, _ = redact(index_note(note), "strict")
    assert texts(kept) == "Next item."


def test_sentences_skip_blank_lines():
    t = "a.\n\nB c."
    assert [t[a:b] for a, b in sentences(t, 0, len(t))] == ["a.", "B c."]
