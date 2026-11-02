# Medicare SNF Coverage: Eligibility Prerequisites

> ⚠️ **AI-GENERATED DOCUMENT. This is not an original policy source.**
> Claude (Anthropic, model `claude-opus-5-5`) wrote this summary through Claude Code on 2026-10-28 and revised it on 2026-11-02. The quotes were copied from the source files listed below, but a person has not yet reviewed this file. Check every citation against the original documents before relying on it. If this file and a source document disagree, the source document is correct.

This file is the human-readable companion to [`criterion_cards_GENERATED.yaml`](criterion_cards_GENERATED.yaml). The YAML cards are the version code should use; each item below names its card ID(s) and its plan criterion (C0–C8 in `plan/snf_pa_consensus_work_plan_1025.md` @ `origin/snf-criterion-cards` e279503). Items marked **BPM only** come from the manual and have no card yet.

## Source files

All files are in `policy_docs/`. Every citation below names its file and version.

| Short name | Document | File | Version |
|---|---|---|---|
| **CFR 409 D** | 42 CFR Part 409, Subpart D, "Requirements for Coverage of Posthospital SNF Care" | `42cfr409_subpartD.xml` | Not stated in the file (eCFR export with a `_SUBSTITUTE_DATE_` placeholder). The original `criterion_cards.YAML` says eCFR 2026-10-01 |
| **CFR 409.61** | 42 CFR 409.61, "General limitations on amount of benefits" | `42cfr409_61_ecfr_2026-10-29.xml` (official PDF: `42cfr409_61_cfr_2025-10-01.pdf`) | eCFR current as of 2026-10-29; text identical to the CFR 10-1-25 Edition |
| **CFR 424.20** | 42 CFR 424.20, "Requirements for posthospital SNF care" | `42cfr424_20_ecfr_2026-10-29.xml` (official PDF: `42cfr424_20_cfr_2025-10-01.pdf`) | eCFR current as of 2026-10-29; text identical to the CFR 10-1-25 Edition |
| **CFR 412.622** | 42 CFR 412.622, "Basis of payment" (IRF coverage criteria in (a)(3)). **Tier 3 background only** | `42cfr412_622_ecfr_2026-10-29.xml` (official PDF: `42cfr412_622_cfr_2025-10-01.pdf`, outdated in places) | eCFR current as of 2026-10-29; amended 2026-08-03 and 2026-10-01. The (a)(3) thresholds match the 10-1-25 Edition |
| **BPM** | Medicare Benefit Policy Manual, Pub. 100-02, Chapter 8 | `bp102c08.pdf` | Rev. 12283, issued 2023-10-05 |
| **FAQ** | CMS HPMS memo, "Frequently Asked Questions related to Coverage Criteria and Utilization Management Requirements in CMS Final Rule (CMS-4201-F)" | `cms_hpms_faq_coverage_criteria_um_2024-02-06.pdf` (on branch `snf-criterion-cards` @ e279503 only) | Dated 2024-02-06. Guidance (Tier 2), not regulation |

Quotes are copied word for word. Block quotes have no outer quotation marks, so quotation marks inside a quote are the source's own. "…" marks omitted text. A patient must meet **every** requirement in Sections 1–6. Section 7 lists rules about what reviewers may *not* use as grounds for denial.

---

## Summary checklist

| Plan | Requirement | Card(s) | Primary citation | Type |
|---|---|---|---|---|
| C0 | Entitled to Medicare Part A in the month of hospital discharge | A2 | CFR 409 D §409.30(a)(2); BPM §20.1 | Structured |
| C1 | Inpatient stay of ≥3 consecutive calendar days (admission day counts, discharge day does not) | A1 | CFR 409 D §409.30(a)(1); BPM §20.1 | Structured |
| C1 | Observation / ER time does not count toward the 3 days | BPM only | BPM §10, §20.1 | Structured |
| C1 | The qualifying stay was medically necessary | A1 | CFR 409 D §409.30(a)(1); BPM §20.1 | Mostly presumed |
| C1 | Stay was in a participating / qualified hospital or CAH | A1 | CFR 409 D §409.30(a)(1); BPM §20.1 | Structured |
| C2 | SNF admission within 30 days of hospital discharge | A3 | CFR 409 D §409.30(b)(1); BPM §20.2.1 | Structured |
| C2 | Exception: deferred care that was medically predictable | A4 | CFR 409 D §409.30(b)(2)(i); BPM §20.2.2 | Clinical |
| C1–C3 | Exception: Medicare Advantage enrollees deemed to meet the stay, timing and related-condition rules | A5 | CFR 409 D §409.30(b)(2)(ii) | Structured |
| — | Readmission in the same benefit period | A20 | CFR 409 D §409.36; BPM §20.2.3 | Structured |
| C3 | SNF care is for a condition treated during the hospital stay | A9 | CFR 409 D §409.31(b)(2); BPM §20.1 | Clinical |
| C4 | Needs skilled nursing or skilled rehab services, ordered by a physician | A7, A11–A17 | CFR 409 D §409.31(a), §409.32, §409.33; BPM §30, §30.2–30.5 | Clinical |
| C5 | Needs those services on a daily basis | A8, A18 | CFR 409 D §409.31(b)(1), §409.34; BPM §30.6 | Clinical |
| C6 | As a practical matter, care can only be given inpatient in a SNF | A10, A19 | CFR 409 D §409.31(b)(3), §409.35; BPM §30.7 | Clinical/social |
| C4 | Services are reasonable and necessary | BPM only | BPM §30, §30.2.2.1 | Clinical |
| C4–C6 | Level of care presumed through the initial assessment (after admission) | A6 | CFR 409 D §409.30 (intro); BPM §30.1 | Structured |
| C7 | Physician (or NP/CNS/PA) certification of need for daily SNF care | A22 | CFR 424.20; BPM §40, §40.1 | Documentation |
| C8 | SNF benefit days left in the benefit period | A21 | CFR 409.61(b), (c) | Benefit limit |

---

## 1. Pre-admission (qualifying hospital stay) requirements

### C0 · Medicare Part A entitlement at the time of hospital discharge — card A2

The beneficiary must be 65 or older, or entitled to Medicare because of disability or ESRD, in the month of hospital discharge.

> Have been discharged from the hospital or CAH in or after the month he or she attained age 65, or in a month for which he or she was entitled to hospital insurance benefits on the basis of disability or end-stage renal disease, in accordance with part 406 of this chapter.
>
> — 42 CFR 409.30(a)(2) · `42cfr409_subpartD.xml` (undated)

> the hospital discharge must have occurred on or after the first day of the month in which the individual attained age 65 or, effective July 1, 1973, became entitled to health insurance benefits under the disability or chronic renal disease provisions of the law.
>
> — BPM Ch. 8 §20.1 · `bp102c08.pdf` Rev. 12283

**Note for the project:** the plan's C0 proxy (Medicare insurance and age ≥65 at admission) differs from the regulation: the regulation tests the discharge month, the cohort excludes disability and ESRD entitlement, and the insurance field does not show Part A or separate FFS from MA (plan @ e279503, lines 194, 278).

### C1 · At least 3 consecutive calendar days as an inpatient — card A1

> Have been hospitalized in a participating or qualified hospital or participating CAH, for medically necessary inpatient hospital or inpatient CAH care, for at least 3 consecutive calendar days, not counting the date of discharge
>
> — 42 CFR 409.30(a)(1) · `42cfr409_subpartD.xml` (undated)

Counting rules:

> The 3 consecutive calendar day stay requirement can be met by stays totaling 3 consecutive days in one or more hospitals. In determining whether the requirement has been met, the day of admission, but not the day of discharge, is counted as a hospital inpatient day.
>
> — BPM Ch. 8 §20.1 · `bp102c08.pdf` Rev. 12283

> For purposes of the SNF benefit's qualifying hospital stay requirement, inpatient status commences with the calendar day of hospital admission.
>
> — BPM Ch. 8 §10 and §20.1 · `bp102c08.pdf` Rev. 12283

Days when the patient waits in the hospital for a SNF bed ("alternate placement" days) also count:

> such additional, "alternate placement" days spent in the hospital can be included in the 3-day count toward meeting the SNF benefit's qualifying hospital stay requirement.
>
> — BPM Ch. 8 §20.1 · `bp102c08.pdf` Rev. 12283

The level of care at the end of the stay does not affect the count:

> the level of care being furnished at that particular point is not a determining factor as long as some portion of the stay included at least 3 consecutive days of medically necessary inpatient hospital services.
>
> — BPM Ch. 8 §20.1, repeated in §20.2.1 · `bp102c08.pdf` Rev. 12283

### C1 · Observation and emergency-room time do not count — BPM only

> Time spent in observation or in the emergency room prior to (or in lieu of) an inpatient admission to the hospital does not count toward the 3-day qualifying inpatient hospital stay, as a person who appears at a hospital's emergency room seeking examination or treatment or is placed on observation has not been admitted to the hospital as an inpatient; instead, the person receives outpatient services.
>
> — BPM Ch. 8 §10 and §20.1 · `bp102c08.pdf` Rev. 12283

### C1 · The qualifying hospital stay was medically necessary — card A1

> the qualifying hospital stay must have been medically necessary. Medical necessity will generally be presumed to exist. … The A/B MAC will rule the stay unnecessary only when hospitalization for 3 days represents a substantial departure from normal medical practice.
>
> — BPM Ch. 8 §20.1 · `bp102c08.pdf` Rev. 12283

### C1 · The hospital is a participating or qualifying facility — card A1

> the hospital must be either a Medicare-participating hospital or an institution that meets at least the conditions of participation for an emergency services hospital
>
> — BPM Ch. 8 §20.1 · `bp102c08.pdf` Rev. 12283

Exclusion:

> Stays in Religious Nonmedical Health Care Institutions … are excluded for the purpose of satisfying the 3-day period of hospitalization.
>
> — BPM Ch. 8 §20.1 · `bp102c08.pdf` Rev. 12283

A stay in a psychiatric hospital counts toward the 3 days, but a patient with only a psychiatric condition will likely not receive covered SNF care:

> While a 3-day stay in a psychiatric hospital satisfies the prior hospital stay requirement, institutions that primarily provide psychiatric treatment cannot participate in the program as SNFs. Therefore, a patient with only a psychiatric condition who is transferred from a psychiatric hospital to a participating SNF is likely to receive only non-covered care.
>
> — BPM Ch. 8 §20.1 (NOTE) · `bp102c08.pdf` Rev. 12283

---

## 2. Timing of SNF admission

### C2 · Admitted to the SNF and receiving needed care within 30 days of discharge — card A3

> the beneficiary must be in need of posthospital SNF care, be admitted to the facility, and receive the needed care within 30 calendar days after the date of discharge from a hospital or CAH.
>
> — 42 CFR 409.30(b)(1) · `42cfr409_subpartD.xml` (undated)

> In determining the 30-day transfer period, the day of discharge from the hospital is not counted in the 30 days. For example, a patient discharged from a hospital on August 1 and admitted to a SNF on August 31 was admitted within 30 days.
>
> — BPM Ch. 8 §20.2.1 · `bp102c08.pdf` Rev. 12283

The patient must need a covered level of care within the 30 days. Being admitted within that window is not enough:

> an individual who is admitted to a SNF within 30 days after discharge from a hospital, but does not require a covered level of care until more than 30 days after such discharge, does not meet the 30-day requirement.
>
> — BPM Ch. 8 §20.2.1 · `bp102c08.pdf` Rev. 12283

### C2 · Exception: deferred care that is medically appropriate and predictable — card A4

> A beneficiary for whom posthospital SNF care would not be medically appropriate within 30 days after discharge from the hospital or CAH, or a beneficiary enrolled in a Medicare + Choice (M + C) plan, may be admitted at the time it would be medically appropriate to begin an active course of treatment.
>
> — 42 CFR 409.30(b)(2)(i) · `42cfr409_subpartD.xml` (undated)

> to qualify for this exception it must be medically predictable at the time of hospital discharge that a covered level of SNF care will be required within a predictable period of time for the treatment of a condition for which hospital care was received and the patient must begin receiving such care within that time frame.
>
> — BPM Ch. 8 §20.2.2.1 · `bp102c08.pdf` Rev. 12283 (example: hip fracture, with SNF admission 4–6 weeks later once the patient can bear weight)

The exception does **not** apply when the need is unpredictable:

> When a patient's medical needs and the course of treatment are not predictable at the time of hospital discharge … an admission to a SNF more than 30 days after discharge from the hospital is not justified under this exception to the 30-day rule.
>
> — BPM Ch. 8 §20.2.2.2 · `bp102c08.pdf` Rev. 12283

### C1–C3 · Medicare Advantage (M+C) enrollees — card A5

> If, upon admission to the SNF, the beneficiary was enrolled in an M + C plan … offering the benefits described in § 422.101(c) of this chapter, the beneficiary will be considered to have met the requirements described in paragraphs (a) and (b) of this section, and also in § 409.31(b)(2), for the duration of the SNF stay.
>
> — 42 CFR 409.30(b)(2)(ii) · `42cfr409_subpartD.xml` (undated)

**Note for the project:** this means MA plans *may* waive the 3-day stay, 30-day transfer, and related-condition rules (C1–C3). Read literally, paragraph (a) also includes the C0 entitlement rule. The level-of-care rules in Section 4 still apply.

### Readmission after a SNF discharge (same benefit period) — card A20

> he or she is not entitled to additional services of this kind in the same benefit period unless— (a) He or she is readmitted to the same or another facility within 30 calendar days following the day of discharge …; or (b) He or she is again hospitalized for at least 3 consecutive calendar days.
>
> — 42 CFR 409.36 · `42cfr409_subpartD.xml` (undated); see also BPM Ch. 8 §20.2.3 · `bp102c08.pdf` Rev. 12283

---

## 3. Related-condition requirement

### C3 · SNF care is for a condition related to the qualifying stay — card A9

> Those services must be furnished for a condition— (i) For which the beneficiary received inpatient hospital or inpatient CAH services; or (ii) Which arose while the beneficiary was receiving care in a SNF or swing-bed hospital for a condition for which he or she received inpatient hospital or inpatient CAH services; or (iii) For which, for an M + C enrollee described in § 409.20(c)(4), a physician has determined that a direct admission to a SNF without an inpatient hospital or inpatient CAH stay would be medically appropriate.
>
> — 42 CFR 409.31(b)(2) · `42cfr409_subpartD.xml` (undated)

Item (iii) lets an MA enrollee go to a SNF directly, without a hospital stay, when a physician finds that appropriate. (The 2026-10-28 version of this file left it out.)

The condition does **not** have to be the principal diagnosis:

> the applicable hospital condition need not have been the principal diagnosis that actually precipitated the beneficiary's admission to the hospital, but could be any one of the conditions present during the qualifying hospital stay.
>
> — BPM Ch. 8 §20.1 · `bp102c08.pdf` Rev. 12283

---

## 4. Level-of-care requirements (all four must be met)

> Care in a SNF is covered if all of the following four factors are met … If any one of these four factors is not met, a stay in a SNF, even though it might include the delivery of some skilled services, is not covered.
>
> — BPM Ch. 8 §30 · `bp102c08.pdf` Rev. 12283

Order of review:

> the A/B MAC (A) first considers whether a patient needs skilled care. If a need for a skilled service does not exist, then the "daily" and "practical matter" requirements are not addressed.
>
> — BPM Ch. 8 §30 · `bp102c08.pdf` Rev. 12283

### C4 · Needs skilled nursing and/or skilled rehabilitation services, ordered by a physician — cards A7, A11–A17

> The beneficiary must require skilled nursing or skilled rehabilitation services, or both, on a daily basis.
>
> — 42 CFR 409.31(b)(1) · `42cfr409_subpartD.xml` (undated) — card A8

Definition: services that

> (1) Are ordered by a physician; (2) Require the skills of technical or professional personnel such as registered nurses, licensed practical (vocational) nurses, physical therapists, occupational therapists, and speech pathologists or audiologists; and (3) Are furnished directly by, or under the supervision of, such personnel.
>
> — 42 CFR 409.31(a) · `42cfr409_subpartD.xml` (undated); see also BPM Ch. 8 §30.2.1 · `bp102c08.pdf` Rev. 12283

Test for whether a service is skilled:

> To be considered a skilled service, the service must be so inherently complex that it can be safely and effectively performed only by, or under the supervision of, professional or technical personnel.
>
> — 42 CFR 409.32(a) · `42cfr409_subpartD.xml` (undated) — card A11

Special medical complications can make a usually non-skilled service skilled (card A12):

> In situations of this type, the complications, and the skilled services they require, must be documented by physicians' orders and nursing or therapy notes.
>
> — 42 CFR 409.32(b) · `42cfr409_subpartD.xml` (undated)

Skilled care can maintain the patient's condition. It does not have to improve it:

> Skilled care may be necessary to improve a patient's current condition, to maintain the patient's current condition, or to prevent or slow further deterioration of the patient's condition.
>
> — BPM Ch. 8 §30.2.1 · `bp102c08.pdf` Rev. 12283

Several non-skilled services can together require skilled management:

> it is necessary to determine whether individual services are skilled, and whether, in light of the patient's total condition, skilled management of the services provided is needed even though many or all of the specific services were unskilled.
>
> — BPM Ch. 8 §30.2.2 · `bp102c08.pdf` Rev. 12283; see also 42 CFR 409.33(a)(1) · `42cfr409_subpartD.xml` (card A14.1) and BPM §30.2.3.1

The qualifying skilled services and the non-qualifying personal-care services are listed in the [Appendix](#appendix-skilled-vs-non-skilled-services) for evidence extraction.

### C5 · Needs skilled services on a daily basis — cards A8, A18

> (1) Skilled nursing services or skilled rehabilitation services must be needed and provided 7 days a week; or (2) As an exception, if skilled rehabilitation services are not available 7 days a week those services must be needed and provided at least 5 days a week.
>
> — 42 CFR 409.34(a) · `42cfr409_subpartD.xml` (undated)

> A patient whose inpatient stay is based solely on the need for skilled rehabilitation services would meet the "daily basis" requirement when they need and receive those services on at least 5 days a week. (If therapy services are provided less than 5 days a week, the "daily" requirement would not be met.)
>
> — BPM Ch. 8 §30.6 · `bp102c08.pdf` Rev. 12283

Short breaks are allowed:

> A break of one or two days in the furnishing of rehabilitation services will not preclude coverage if discharge would not be practical for the one or two days
>
> — 42 CFR 409.34(b) · `42cfr409_subpartD.xml` (undated)

Restorative nursing programs:

> In instances when a patient requires a skilled restorative nursing program to positively affect his functional well-being, the expectation is that the program be rendered at least 6 days a week.
>
> — BPM Ch. 8 §30.6 · `bp102c08.pdf` Rev. 12283

Intermittent need does not qualify:

> payment for a SNF level of care could not be made if a patient needs an intermittent rather than daily skilled service.
>
> — BPM Ch. 8 §30 · `bp102c08.pdf` Rev. 12283

### C6 · "Practical matter": the daily skilled care can only be provided inpatient in a SNF — cards A10, A19

> The daily skilled services must be ones that, as a practical matter, can only be provided in a SNF, on an inpatient basis.
>
> — 42 CFR 409.31(b)(3) · `42cfr409_subpartD.xml` (undated)

> As a "practical matter," daily skilled services can be provided only in a SNF if they are not available on an outpatient basis in the area in which the individual resides or transportation to the closest facility would be: • An excessive physical hardship; • Less economical; or • Less efficient or effective than an inpatient institutional setting.
>
> — BPM Ch. 8 §30.7 · `bp102c08.pdf` Rev. 12283; see also 42 CFR 409.35(b) · `42cfr409_subpartD.xml` (undated)

The home support situation counts:

> The availability of capable and willing family or the feasibility of obtaining other assistance for the patient at home should be considered. … the care can be furnished only in the SNF if home care would be ineffective because the patient would have insufficient assistance at home to reside there safely.
>
> — BPM Ch. 8 §30.7 · `bp102c08.pdf` Rev. 12283

Not being able to walk is not enough by itself:

> Determinations on whether a patient's condition would be adversely affected if an available, more economical care alternative were utilized should not be based solely on the fact that the patient is nonambulatory.
>
> — BPM Ch. 8 §30.7.3 · `bp102c08.pdf` Rev. 12283

### C4 · Services are reasonable and necessary — BPM only

> The services delivered are reasonable and necessary for the treatment of a patient's illness or injury, i.e., are consistent with the nature and severity of the individual's illness or injury, the individual's particular medical needs, and accepted standards of medical practice. The services must also be reasonable in terms of duration and quantity.
>
> — BPM Ch. 8 §30 · `bp102c08.pdf` Rev. 12283

Documentation needed to show this:

> Claims for skilled care coverage need to include sufficient documentation to enable a reviewer to determine whether— • Skilled involvement is required in order for the services in question to be furnished safely and effectively; and • The services themselves are, in fact, reasonable and necessary
>
> — BPM Ch. 8 §30.2.2.1 · `bp102c08.pdf` Rev. 12283

Vague notes do not count as evidence:

> the following terminology does not sufficiently describe the reaction of the patient to his/her skilled care: • Patient tolerated treatment well • Continue with POC • Patient remains stable
>
> — BPM Ch. 8 §30.2.2.1 · `bp102c08.pdf` Rev. 12283

### C4–C6 · Administrative level-of-care presumption (first ~8 days) — card A6

If the patient is admitted directly from a qualifying stay and is correctly assigned a designated case-mix classifier, level of care is presumed through the initial assessment:

> A beneficiary in an SNF is also considered to meet the level of care requirements of § 409.31 up to and including the assessment reference date for the initial Medicare assessment prescribed in § 413.343(b) of this chapter, when correctly assigned one of the case-mix classifiers that CMS designates for this purpose as representing the required level of care. … the assessment reference date … must be set for no later than the eighth day of posthospital SNF care.
>
> — 42 CFR 409.30 (introductory text) · `42cfr409_subpartD.xml` (undated)

> If the beneficiary is not admitted (or readmitted) directly to a SNF after a qualifying hospital stay, the administrative level of care presumption does not apply.
>
> — BPM Ch. 8 §30.1 · `bp102c08.pdf` Rev. 12283

**Note for the project:** the presumption applies after admission, so a prior-auth review made before admission cannot rely on it.

---

## 5. Physician certification

### C7 · Signed certification that the patient needs daily SNF-level care — card A22

> Medicare Part A pays for posthospital SNF care furnished by an SNF, or a hospital or CAH with a swing-bed approval, only if the certification and recertification for services are consistent with the content of paragraph (a) or (c) of this section, as appropriate.
>
> — 42 CFR 424.20 (introductory text) · `42cfr424_20_ecfr_2026-10-29.xml`

What the certification must say: the patient needs daily skilled care that can only be given inpatient in a SNF, for a condition treated in the hospital (or one that arose during SNF care for it), **or** the patient has been correctly assigned a CMS-designated case-mix classifier (42 CFR 424.20(a)(1)). This restates C3–C6, so C7 is a documentation check, not a separate clinical test.

Timing:

> The certification must be obtained at the time of admission or as soon thereafter as is reasonable and practicable.
>
> — 42 CFR 424.20(b)(1) · `42cfr424_20_ecfr_2026-10-29.xml`

> (1) The first recertification is required no later than the 14th day of posthospital SNF care. (2) Subsequent recertifications are required at least every 30 days after the first recertification.
>
> — 42 CFR 424.20(d) · `42cfr424_20_ecfr_2026-10-29.xml`

An admission order is not enough:

> The routine admission order established by a physician is not a certification … There must be a separate signed statement indicating that the patient will require on a daily basis SNF covered care.
>
> — BPM Ch. 8 §40 · `bp102c08.pdf` Rev. 12283

Who may sign:

> A certification or recertification statement must be signed by the attending physician or a physician on the staff of the skilled nursing facility who has knowledge of the case, or by a physician extender (that is, a nurse practitioner (NP), a clinical nurse specialist (CNS) or … a physician assistant (PA)) who does not have a direct or indirect employment relationship with the facility
>
> — BPM Ch. 8 §40.1 · `bp102c08.pdf` Rev. 12283; see also 42 CFR 424.20(e) · `42cfr424_20_ecfr_2026-10-29.xml`

**Note for the project:** a missing certification should lead to PEND / request for information, not a clinical denial. MIMIC has no certification data, so the plan sets C7 to "assumed submitted" (plan @ e279503, line 285).

---

## 6. Benefit days

### C8 · SNF benefit days left in the benefit period — card A21

> Up to 100 days are available in each benefit period after discharge from a hospital or CAH. For the first 20 days, Medicare pays for all covered services. For the 21st through 100th day, Medicare pays for all covered services except for a daily coinsurance amount that is the beneficiary's responsibility.
>
> — 42 CFR 409.61(b) · `42cfr409_61_ecfr_2026-10-29.xml`

> The beneficiary's full entitlement to the 90 inpatient hospital or inpatient CAH regular benefit days, and the 100 SNF benefit days, is renewed each time he or she begins a benefit period.
>
> — 42 CFR 409.61(c) · `42cfr409_61_ecfr_2026-10-29.xml`

**Note for the project:** this decides how many days are paid, not whether the patient qualifies, so treat it as an intake check rather than a reviewer criterion. MIMIC shows only one hospital, so the plan assumes it is met (plan @ e279503, line 202). MA plans may set their own day limits and cost sharing. The definition of "benefit period" (42 CFR 409.60), SNF coinsurance (42 CFR 409.85) and BPM Chapter 3 are not in `policy_docs/`.

---

## 7. Guardrails: factors that must NOT decide a case

These rules matter for the QA/Critic agent.

### Improvement potential is not the deciding factor (Jimmo v. Sebelius) — card A13

> The restoration potential of a patient is not the deciding factor in determining whether skilled services are needed. Even if full recovery or medical improvement is not possible, a patient may need skilled services to prevent further deterioration or preserve current capabilities.
>
> — 42 CFR 409.32(c) · `42cfr409_subpartD.xml` (undated)

> Coverage of nursing care and/or therapy to perform a maintenance program does not turn on the presence or absence of an individual's potential for improvement from the nursing care and/or therapy, but rather on the beneficiary's need for skilled care.
>
> — BPM Ch. 8 §30 · `bp102c08.pdf` Rev. 12283; see also §30.3, §30.4

### IRF criteria are not SNF criteria — cards G6, X1

An inpatient rehabilitation facility (IRF) has stricter rules than a SNF. Reviewers sometimes apply them to SNF requests by mistake. For IRF coverage, the patient must need several therapy disciplines (one of them PT or OT), be able to take part in an intensive program, and show measurable improvement:

> Under current industry standards, this intensive rehabilitation therapy program generally consists of at least 3 hours of therapy (physical therapy, occupational therapy, speech-language pathology, or prosthetics/orthotics therapy) per day at least 5 days per week. … Benefit from this intensive rehabilitation therapy program is demonstrated by measurable improvement that will be of practical value to the patient in improving the patient's functional capacity or adaptation to impairments.
>
> — 42 CFR 412.622(a)(3)(ii) · `42cfr412_622_ecfr_2026-10-29.xml` — Tier 3 background, never a basis for a SNF decision

None of these is a SNF requirement. SNF rehab only has to be needed and given at least 5 days a week (42 CFR 409.34(a)(2), card A18), and improvement is not required (42 CFR 409.32(c), card A13). So a SNF request must not be denied or pended because the patient cannot tolerate 3 hours a day, needs only one discipline, or is not expected to improve. A SNF decision should never cite 42 CFR 412.622.

### Diagnosis or prognosis alone cannot rule out skilled care — BPM only

> While a patient's particular medical condition is a valid factor in deciding if skilled services are needed, a patient's diagnosis or prognosis should never be the sole factor in deciding that a service is not skilled.
>
> — BPM Ch. 8 §30.2.2 · `bp102c08.pdf` Rev. 12283

### Whether an alternative setting is paid for does not count — card A19

> the availability of Medicare payment for those services may not be a factor.
>
> — 42 CFR 409.35(a) · `42cfr409_subpartD.xml` (undated)

> In determining the availability of alternate facilities or services, whether the patient or another resource can pay for the alternate services is not a factor to be considered.
>
> — BPM Ch. 8 §30.7.1 · `bp102c08.pdf` Rev. 12283

### Frequency, importance, or risk of a service does not make it skilled — BPM only

> The importance of a particular service to an individual patient, or the frequency with which it must be performed, does not, by itself, make it a skilled service.
>
> — BPM Ch. 8 §30.2.2 · `bp102c08.pdf` Rev. 12283

> A service is not considered a skilled nursing service merely because it is performed by or under the direct supervision of a nurse. … the unavailability of a competent person to provide a nonskilled service … does not make it a skilled service when a nurse provides the service.
>
> — BPM Ch. 8 §30.3 · `bp102c08.pdf` Rev. 12283

### Cases that need specific supporting evidence ("questionable situations") — BPM only

> There must be specific evidence that daily skilled nursing or skilled rehabilitation services are required and received if: • The primary service needed is oral medication; or • The patient is capable of independent ambulation, dressing, feeding, and hygiene.
>
> — BPM Ch. 8 §30.2.4 · `bp102c08.pdf` Rev. 12283

### Custodial care is never covered — BPM only

> Custodial care … is not a covered extended care service.
>
> — BPM Ch. 8 §50, Note 1 · `bp102c08.pdf` Rev. 12283

### Medicare Advantage decision-making rules — cards G1–G5

These come from the CMS FAQ. It is guidance (Tier 2); the binding rule is the 42 CFR 422 section named on each card.

**Decide on the individual patient, not population predictions (card G1, 42 CFR 422.101(c)):**

> an algorithm that determines coverage based on a larger data set instead of the individual patient's medical history, the physician's recommendations, or clinical notes would not be compliant with § 422.101(c).
>
> — FAQ Q2 · `cms_hpms_faq_coverage_criteria_um_2024-02-06.pdf` (2024-02-06)

> an algorithm or software tool can be used to assist providers or MA plans in predicting a potential length of stay, but that prediction alone cannot be used as the basis to terminate post-acute care services.
>
> — FAQ Q2 · `cms_hpms_faq_coverage_criteria_um_2024-02-06.pdf` (2024-02-06)

**No denial or redirection when the SNF criteria are met (card G2, 42 CFR 422.101(b), (c)):**

> if a patient is being discharged from an acute care hospital to a post-acute care facility that would be covered under Traditional Medicare and the patient's attending physician orders post-acute care in the specific type of facility (i.e., Skilled Nursing Facility (SNF), Long Term Care Hospital (LTCH)) and the patient meets all applicable Medicare coverage criteria for admission into that facility type, the MA organization cannot deny admission to that post-acute setting and/or redirect the care to a different setting.
>
> — FAQ Q7 · `cms_hpms_faq_coverage_criteria_um_2024-02-06.pdf` (2024-02-06)

**Adverse decisions need professional review (card G3, 42 CFR 422.566(d)):**

> if the MA organization expects to issue a partially or fully adverse decision about whether the services are or were medically necessary, that decision – meaning that organization determination - must be reviewed by a physician or other appropriate health care professional with expertise in the field of medicine or health care that is appropriate for the services at issue, including knowledge of Medicare coverage criteria, before the MA organization issues the organization determination decision.
>
> — FAQ Q9 · `cms_hpms_faq_coverage_criteria_um_2024-02-06.pdf` (2024-02-06)

**Interrupted SNF stay: no new prior authorization within 3 days (card G4, 42 CFR 422.112(b)(8)(i)(A)):**

> MA organizations that offer coordinated care plans must not require another prior authorization when a patient returns no more than three consecutive calendar days after having been discharged and the patient is still undergoing the same course of treatment that was previously approved.
>
> — FAQ Q10 · `cms_hpms_faq_coverage_criteria_um_2024-02-06.pdf` (2024-02-06)

**Termination notices must explain the criteria (card G5, 42 CFR 422.626(c), (e)):**

> the MA organization must supply a specific and detailed explanation why services are either no longer reasonable and necessary or are no longer covered, including a description of the applicable coverage criteria and rules.
>
> — FAQ Q7 · `cms_hpms_faq_coverage_criteria_um_2024-02-06.pdf` (2024-02-06)

The FAQ states G5 for terminations. Applying it to initial prior-auth decision letters is a project choice.

---

## Appendix: Skilled vs. non-skilled services

### Qualifying skilled nursing services — card A15

Sources: 42 CFR 409.33(b) · `42cfr409_subpartD.xml` (undated); BPM Ch. 8 §30.3 · `bp102c08.pdf` Rev. 12283.

| Service | Citation note |
|---|---|
| IV or IM injections; IV feeding | CFR §409.33(b)(1) |
| Enteral feeding ≥26% of daily calories **and** ≥501 mL fluid/day | CFR §409.33(b)(2) |
| Nasopharyngeal and tracheostomy aspiration | CFR §409.33(b)(3) |
| Insertion, sterile irrigation, replacement of suprapubic catheters | CFR §409.33(b)(4) |
| Dressings involving prescription medications and aseptic technique | CFR §409.33(b)(5) |
| Treatment of decubitus ulcers **Stage 3 or worse**, or widespread skin disorder | BPM §30.3 (CFR §409.33(b)(6) says "extensive") |
| Physician-ordered heat treatments requiring nurse observation | CFR §409.33(b)(7) |
| Initial phases of medical-gas regimen (e.g., bronchodilator therapy) | CFR §409.33(b)(8); BPM §30.3 |
| Rehabilitation nursing (e.g., bowel/bladder training) | CFR §409.33(b)(9) |
| Early post-op colostomy care with complications | BPM §30.3 |

### Services that can be skilled nursing or skilled rehab — card A14

Sources: 42 CFR 409.33(a) · `42cfr409_subpartD.xml` (undated); BPM Ch. 8 §30.2.3 · `bp102c08.pdf` Rev. 12283.

| Service | Example from policy | Card | Citation |
|---|---|---|---|
| Management and evaluation of the care plan | Post-hip-fracture patient with diabetes and angina | A14.1 | CFR §409.33(a)(1); BPM §30.2.3.1 |
| Observation and assessment of a changing condition | CHF decompensation watch; post-op hip; post-MI mobilization; poor oral intake after pneumonia | A14.2 | CFR §409.33(a)(2); BPM §30.2.3.2 |
| Patient education / training | New insulin user; new amputee gait and prosthesis training; new ostomy care | A14.3 | CFR §409.33(a)(3); BPM §30.2.3.3 |

Signals that support skilled observation:

> Such signs and symptoms as abnormal/fluctuating vital signs, weight changes, edema, symptoms of drug toxicity, abnormal/fluctuating lab values, and respiratory changes on auscultation may justify skilled observation and assessment.
>
> — BPM Ch. 8 §30.2.3.2 · `bp102c08.pdf` Rev. 12283

### Qualifying skilled rehabilitation services — card A16

Sources: 42 CFR 409.33(c) · `42cfr409_subpartD.xml` (undated); BPM Ch. 8 §30.4 · `bp102c08.pdf` Rev. 12283.

| Service | Citation |
|---|---|
| Ongoing assessment of rehab needs (ROM, strength, balance, ADLs, speech, etc.) | CFR §409.33(c)(1) |
| Therapeutic exercise that needs a PT/OT | CFR §409.33(c)(2) |
| Gait evaluation and training for neuro/muscular/skeletal impairment | CFR §409.33(c)(3) |
| ROM exercises as active treatment of a specific loss of mobility | CFR §409.33(c)(4) |
| Design/establishment of a maintenance program by a qualified therapist | CFR §409.33(c)(5); BPM §30.4.1.2.E |
| Ultrasound, short-wave, microwave therapy by a PT | CFR §409.33(c)(6) |
| Hot pack/whirlpool etc. **only with** complications (circulatory deficiency, open wounds, fractures) | CFR §409.33(c)(7) |
| Speech-language pathology or audiology to restore function | CFR §409.33(c)(8) |

Requirements specific to PT:

> The services must be directly and specifically related to an active written treatment plan that is based upon an initial evaluation performed by a qualified physical therapist after admission to the SNF … The services must be of a level of complexity and sophistication, or the condition of the patient must be of a nature that requires the judgment, knowledge, and skills of a qualified physical therapist
>
> — BPM Ch. 8 §30.4.1.1 · `bp102c08.pdf` Rev. 12283

### NOT skilled (personal / custodial care) — card A17

Sources: 42 CFR 409.33(d) · `42cfr409_subpartD.xml` (undated); BPM Ch. 8 §30.5 · `bp102c08.pdf` Rev. 12283.

Not skilled unless special medical complications require skilled personnel (42 CFR 409.32(b), card A12):

- Routine oral medications, eye drops, ointments
- General maintenance of colostomy/ileostomy
- Routine indwelling catheter care
- Dressing changes for **non-infected** post-op or chronic conditions
- Prophylactic/palliative skin care, minor skin problems
- Routine incontinence care
- General plaster cast care; routine brace care
- Heat used as palliative/comfort measure
- Routine medical gases after the regimen is established
- Help with dressing, eating, toileting
- Periodic turning and positioning
- Supervision of exercises already taught; repetitive gait/strength exercises; passive ROM not tied to a specific loss of function; assistive walking

---

## Out of scope for patient-level eligibility

These parts of BPM Ch. 8 (`bp102c08.pdf` Rev. 12283) apply to the facility or billing, not to whether a patient qualifies:

- §10.1–10.2: SNF PPS and consolidated billing
- §20.3: payment bans on facilities (DPNA)
- §50–§70: lists of covered services, Part B services, and arrangements with outside providers

Deciding whether a patient should go to an IRF instead of a SNF (42 CFR 412.622) is also out of scope (plan @ e279503, line 248). The IRF rules are kept only as background, for the guardrail above and to explain why the plan's REHAB/IRF sample group is expected to meet SNF C4/C5.

## Changes since the 2026-10-28 version

- Every citation now names its source file and version.
- Items are labelled by plan criterion (C0–C8) and YAML card ID. The old A1–E1 / F1–F6 labels were removed because they clashed with the card IDs.
- Added: 42 CFR 409.31(b)(2)(iii) (MA direct admission), 42 CFR 424.20 text for C7, a new Section 6 for C8 (42 CFR 409.61), the 42 CFR 409.30 text for the level-of-care presumption, 42 CFR 409.32(b) documentation rule, and the CMS FAQ guardrails (cards G1–G5).
- Benefit-day limits moved from "out of scope" to Section 6.
- Added 42 CFR 412.622 (IRF coverage criteria) as Tier 3 background, with the guardrail "IRF criteria are not SNF criteria" (cards X1, G6).
- Four BPM quotes used single quotation marks where the manual uses double; they now match the manual. Outer quotation marks were dropped from block quotes.
