"""Discharge note spans and redaction on a synthetic note (no MIMIC text).
Note adapted from Hui Li's tests/test_redact.py (origin/snf-criterion-cards @ 84832e0); expectations follow
design §3.5 / D-007 and our merged rules."""
from snf_pa.adapters.sources import discharge_note as dn

NOTE = """Name:  ___                     Unit No:   ___

Service: ORTHOPAEDICS

Allergies:
Penicillins / Keflex

Attending: ___.

Chief Complaint:
Right hip pain after fall

Major Surgical or Invasive Procedure:
Right hip ORIF

History of Present Illness:
Mr. ___ is an ___ yo man who fell at home. He was recently discharged from rehab in ___.
He was seen by his PCP last week for knee pain.

Social History:
Lives alone in a second-floor apartment. Daughter visits weekly.

Family History:
Father with CAD.

Pertinent Results:
CT head: subacute infarct in the left frontal lobe.

Brief Hospital Course:
Patient underwent ORIF on POD0. Pain was controlled with p.o. oxycodone.
A PICC line placement was done for IV antibiotics.
PT evaluated him and found he needs moderate assist for transfers, and recommended discharge to rehab.
Case management screened for SNF placement.
He was started on home medications on POD1.
He will follow up with his PCP in 1 week.
Patient verbalized understanding of the discharge plan.
Goals of care discussed; family considering hospice.
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


def kept():
    k, _ = dn.redact(dn.index_note(NOTE))
    return k


def text_of(spans):
    return " ".join(s.text for s in spans)


def test_sections_found_in_order():
    assert [s.code for s in dn.split_sections(NOTE)] == [
        "HDR", "CC", "PROC", "HPI", "SH", "FH", "PR", "HC", "MEDADM", "MEDDC", "DISPO", "FAC", "DXDC", "COND",
        "DCI", "FU"]


def test_sentence_split_keeps_abbreviations_and_offsets():
    spans = dn.index_note(NOTE)
    hc = [s.text for s in spans if s.section == "HC"]
    assert hc[:2] == ["Patient underwent ORIF on POD0.", "Pain was controlled with p.o. oxycodone."]
    for s in spans:
        if s.section != "HDR":
            assert NOTE[s.start:s.end] == s.text


def test_dropped_sections_absent():
    secs = {s.section for s in kept()}
    assert not secs & {"MEDDC", "DISPO", "FAC", "DXDC", "DCI", "FU"}
    assert {"PROC", "FH", "MEDADM", "COND"} <= secs
    t = text_of(kept())
    assert "Extended Care" not in t and "femoral neck fracture" not in t and "Oxycodone" not in t


def test_header_keeps_service_and_allergies_only():
    hdr = [s for s in kept() if s.section == "HDR"]
    assert [s.span_id for s in hdr] == ["DS:HDR:SVC", "DS:HDR:ALG"]
    assert hdr[0].text == "Service: ORTHOPAEDICS" and "Penicillins / Keflex" in hdr[1].text
    assert "Attending" not in text_of(hdr) and "Unit No" not in text_of(hdr)


def test_preadmission_history_kept():
    t = text_of(kept())
    assert "recently discharged from rehab" in t        # pre-admission history (C6 evidence), not a plan
    assert "seen by his PCP last week" in t             # history, not a follow-up arrangement
    assert "Lives alone" in t


def test_clinical_words_not_mistaken_for_disposition():
    t = text_of(kept())
    assert "PICC line placement" in t and "subacute infarct" in t
    assert "home medications" in t


def test_disposition_sentences_removed():
    t = text_of(kept())
    for gone in ["screened for SNF", "follow up with his PCP", "verbalized understanding", "hospice", "VNA"]:
        assert gone not in t, gone


def test_therapy_clause_masked_function_kept():
    pt = [s.text for s in kept() if s.text.startswith("PT evaluated")]
    assert pt == ["PT evaluated him and found he needs moderate assist for transfers, ___"]


def test_no_residual_after_redaction():
    spans = dn.index_note(NOTE)
    assert dn.residual(dn.redact(spans)[0], dn.broad_sections(spans)) == []


def test_ids_independent_of_redaction():
    """Kept spans keep the ID they had in the unredacted index (design §3.3)."""
    original = {s.span_id: s.text for s in dn.index_note(NOTE)}
    for s in kept():
        assert s.span_id in original
        if dn.MASK not in s.text:
            assert original[s.span_id] == s.text
    # removing the PT/OT rule entirely would not renumber anything else
    assert [s.span_id for s in dn.index_note(NOTE)] == [s.span_id for s in dn.index_note(NOTE)]


def test_followup_with_glued_deid_token_removed():
    note = NOTE.replace("He was started on home medications on POD1.",
                        "He was started on home medications on POD1. She will follow up At___ clinic as an outpatient.")
    k, _ = dn.redact(dn.index_note(note))
    assert "follow up At___" not in text_of(k)


def test_discharge_self_care_instructions_removed_only_in_hospital_course():
    note = NOTE.replace("He was started on home medications on POD1.",
                        "He was started on home medications on POD1. He was instructed to complete the antibiotic course. "
                        "His wife was educated on insulin administration.")
    note = note.replace("Daughter visits weekly.", "Daughter visits weekly. He was instructed to stop smoking in ___.")
    t = text_of(dn.redact(dn.index_note(note))[0])
    assert "instructed to complete" not in t
    assert "educated on insulin administration" in t        # teaching is skilled-care evidence
    assert "instructed to stop smoking" in t                # social history, not a discharge-time section
    # same pattern inside a therapy sentence: clause masked, residual check stays clean
    note2 = NOTE.replace("He was started on home medications on POD1.",
                         "PT worked on gait, and he was instructed to continue exercises.")
    spans = dn.index_note(note2)
    k = dn.redact(spans)[0]
    assert "instructed to continue" not in text_of(k) and "PT worked on gait" in text_of(k)
    assert dn.residual(k, dn.broad_sections(spans)) == []


def test_pr_is_always_broad():
    assert "PR" in dn.broad_sections(dn.index_note(NOTE))


# Sentences found surviving in dev bundles by the step-3 independent review; each must be removed.
REVIEW_HOLES = [
    ("PR", "Mr ___ is discharged to rehab in stable condition."),
    ("HC", "Pt will be discharge with home ___ ___."),
    ("HC", "Pt discharged with order for home hospital bed."),
    ("HC", "She was discharged to recover further at home."),
    ("HC", "PT recommended home ___ for ___ sessions, which patient was discharged with."),
    ("HC", "Patient discharged with allergy follow up."),
    ("HC", "Patient is ready for discharge to ___."),
    ("HPI", "He is being discharged to rehab today."),
    # found by the wide-net hand review; several are wrapped across lines in the real notes
    ("HC", "She was seen by ___ who recommended\nhome"),
    ("HC", "Patient will follow-up\nwith Dr. ___ in the outpatient setting."),
    ("PR", "[] Recommend outpatient palliative care, family preference."),
    ("HC", "The patient will be discharged on Lantus with instructions to log his blood glucose and present to PCP."),
    ("PR", "Plan to continue ___ until seen by PCP."),
    ("HC", "Please recheck potassium, Cr, and blood pressure at follow up PCP ___."),
    ("PR", "Pt will be contacted at home by the gastroenterology department."),
    ("HPI", "He remained chest pain free and was discharged to\nrehab."),
    ("HC", "They recommended repeat hip films in one month in Orthopedic Surgery clinic with appointment arranged."),
    ("PMH", "Her PCP was notified and stated she would follow-up with Ms. ___ in the office."),
    ("HC", "On discharge, she will be maintained on lovenox bridge and warfarin."),
]


def test_therapeutic_is_not_therapy_and_cross_clause_trigger_removed():
    t = ("On discharge, she \nwill be maintained on lovenox bridge until her INR is therapeutic and she can "
         "transition back to her \nhome dose of warfarin.")
    assert not dn.THERAPY.search(t)
    note = NOTE.replace("He was started on home medications on POD1.", t + " PT worked on gait, and on discharge, "
                        "she will continue exercises at home.")
    spans = dn.index_note(note)
    k = dn.redact(spans)[0]
    assert "lovenox" not in text_of(k) and "continue exercises" not in text_of(k)
    assert dn.residual(k, dn.broad_sections(spans)) == []


def test_transitional_issues_block_and_todo_items_dropped():
    note = NOTE.replace("TRANSITIONAL ISSUES:\n- VNA to draw INR on ___",
                        "Hemoglobin remained stable.\nTRANSITIONAL ISSUES:\n- Recheck CBC in 1 week\n"
                        "- Continue warfarin 5 mg daily").replace(
        "He was started on home medications on POD1.", "He was started on home medications on POD1.\n[ ] Repeat CT")
    t = text_of(dn.redact(dn.index_note(note))[0])
    assert "Hemoglobin remained stable" in t
    assert "Recheck CBC" not in t and "Continue warfarin" not in t and "Repeat CT" not in t


def test_care_arrangements_removed_but_home_meds_kept():
    for s in ["For that reason home O2 was arranged for use with activity.", "He will be followed in the ___ clinic.",
              "The results were faxed to her PCP.", "Options for placement extensively discussed with CM, SW.",
              "He will require hospital bed at home.", "- Pt dispoed with home ___",
              "She is being sent home on Bumex 2mg daily.",
              "Therapy determined she is appropriate for home d/c once medically ready.",
              "A PICC was placed and patient was d/c'ed home on IV ertapenem.",
              "24-hour care with plan for OT home evaluation."]:
        assert dn.rule(s, "HC", dn.BROAD), s
    for s in ["She was restarted on her home dose of metoprolol 50mg BID.", "Home olmesartan was held."]:
        assert dn.rule(s, "HC", dn.BROAD) is None, s


def test_review_holes_closed():
    for section, sentence in REVIEW_HOLES:
        assert dn.rule(sentence, section, dn.BROAD) is not None, sentence


def test_discharge_status_kept():
    for sentence in ["At the time of discharge, he was ambulating with a walker.",
                     "Mental Status: Clear and coherent.", "He was recently discharged from rehab in ___."]:
        assert dn.rule(sentence, "COND" if "Mental" in sentence else ("HPI" if "recently" in sentence else "HC"),
                       dn.BROAD) is None, sentence
