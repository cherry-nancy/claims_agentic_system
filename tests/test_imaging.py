"""Imaging test helpers on synthetic text (no MIMIC text here)."""
from snf_pa.data.imaging import HEADING, compare, copied_runs, timed
from snf_pa.data.redact import is_deletion_of

NOTE = """Pertinent Results:
___ 07:10AM BLOOD WBC-11.2 Hgb-9.8
___ CXR: Left lower lobe consolidation concerning for pneumonia.
___ CT head: No acute intracranial hemorrhage. Chronic small vessel ischemic disease.
IMPRESSION: Normal left ventricular systolic function.

Brief Hospital Course:
Treated for left lower lobe consolidation concerning for pneumonia with ceftriaxone.
"""
REPORTS = [
    {"exam": "CHEST (PA AND LAT)", "hospital_day": 1, "before_cutoff": True,
     "impression": "Left lower lobe consolidation concerning for pneumonia. Discharge to rehab."},
    {"exam": "CT HEAD W/O CONTRAST", "hospital_day": 5, "before_cutoff": False,
     "impression": "No acute intracranial hemorrhage. Chronic small vessel ischemic disease."},
    {"exam": "KNEE (AP, LAT)", "hospital_day": 2, "before_cutoff": True, "impression": "Moderate tricompartmental osteoarthritis."},
]


def test_copied_imaging_is_found_by_content_in_pertinent_results_only():
    runs = copied_runs(NOTE, REPORTS)
    assert [(NOTE[a:b], before) for a, b, before in runs] == [
        ("Left lower lobe consolidation concerning for pneumonia", True),
        ("No acute intracranial hemorrhage. Chronic small vessel ischemic disease", False)]


def test_timed_notes_swap_copied_imaging_for_reports_signed_before_t_pa():
    body, section = timed(NOTE, REPORTS).split(HEADING)
    assert "intracranial" not in body and "WBC-11.2" in body
    assert "Normal left ventricular systolic function." in body  # echo: not radiology, kept
    assert "Treated for left lower lobe consolidation" in body  # outside Pertinent Results
    assert is_deletion_of(body.rstrip(), NOTE)
    assert "CHEST (PA AND LAT) (hospital day 1): Left lower lobe consolidation" in section
    assert "rehab" not in section  # clause rules applied to report text
    assert "osteoarthritis" in section and "intracranial" not in section  # signed after T_pa: left out


def test_comparison_counts_post_t_pa_imaging_and_omitted_reports():
    c = compare(NOTE, REPORTS)
    assert c["copied_chars_before"] > 0 and c["copied_chars_after"] > 0
    assert (c["n_reports_before"], c["n_reports_quoted"], c["n_reports_after"]) == (2, 1, 1)
