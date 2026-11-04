# policy_docs sources

Public CMS / eCFR documents used as the policy RAG corpus. Retrieved 2026-10-31.
eCFR files were requested with the versioner API for date 2026-10-01
(`https://www.ecfr.gov/api/versioner/v1/full/2026-10-01/title-42.xml?part=<part>&section=<section>` or `&subpart=D`).
Citations in each file's trailing bracket list the Federal Register amendments (latest seen: 91 FR 17581, Apr. 6, 2026).

## Tier 1: binding regulation (42 CFR)

| File | Content | Use |
|---|---|---|
| `42cfr409_subpartD.xml` | §§409.30-409.36 SNF coverage (3-day stay, 30 days, skilled services, daily basis, practical matter) | SNF criteria C1-C6 |
| `42cfr422_101.xml` | §422.101 basic benefits: (b)(2) TM criteria incl. SNF part 409, (b)(6) internal criteria, (c)(1) medical necessity, (c)(2) 3-day waiver | what standard MA must apply |
| `42cfr422_112.xml` | §422.112 access; (b)(8) PA approval valid for a course of treatment, 90-day transition | approval validity |
| `42cfr422_122.xml` | §422.122 PA requirements (CMS-0057-F): specific denial reason from 2026-01-01, PA API 2027-01-01, public metrics | denial reasons, API |
| `42cfr422_137.xml` | §422.137 UM committee | governance |
| `42cfr422_138.xml` | §422.138 PA purposes, effect of approval (no later medical-necessity denial) | PA limits |
| `42cfr422_202.xml` | §422.202 participation procedures (UM / physician input) | background |
| `42cfr422_566.xml` | §422.566 organization determinations; (d) who must review adverse medical-necessity decisions | reviewer rule |
| `42cfr422_568.xml` | §422.568 standard timeframes (7 days for PA items from 2026-01-01, 14 days otherwise), denial notice content | timeframes, notice |
| `42cfr422_570.xml` | §422.570 expediting requests | expedited |
| `42cfr422_572.xml` | §422.572 expedited timeframes (72 hours), notice | expedited |
| `42cfr422_582.xml` | §422.582 request for standard reconsideration (60 days to file) | appeals |
| `42cfr422_590.xml` | §422.590 reconsideration timeframes and who decides | appeals |
| `42cfr422_592.xml` | §422.592 reconsideration by independent entity | appeals |
| `42cfr422_624.xml` | §422.624 notice of termination of provider services | termination |
| `42cfr422_626.xml` | §422.626 fast-track appeals of service terminations; burden of proof on MA org | termination |

## Tier 2: guidance

| File | Source |
|---|---|
| `bp102c08.pdf` | Medicare Benefit Policy Manual Ch.8, Rev. 12283 (issued 2023-10-05): https://www.cms.gov/regulations-and-guidance/guidance/manuals/downloads/bp102c08pdf.pdf |
| `cms_hpms_faq_coverage_criteria_um_2024-02-06.pdf` | HPMS memo, Feb 6, 2024, "FAQs related to Coverage Criteria and UM Requirements in CMS-4201-F": https://www.cms.gov/files/document/hpms-memo-faq-coverage-criteria-and-utilization-management-020604pdf.pdf |
| `cms_hpms_faq_coverage_criteria_um_2024-02-06.txt` | Plain-text extraction of the PDF above (pypdf, 14 pages); page markers `[pN]` added. Q2 algorithms/AI, Q7 post-acute admission, Q8 two-midnight, Q10 interrupted stay, Q11 PA / UM committee |

## Notes
- The FAQ is sub-regulatory guidance; later CMS guidance may supersede it (not checked).
- `bp102c08.pdf` is Rev. 12283; not yet checked against the current CMS version.
- Not downloaded: CMS-0057-F / CMS-4201-F Federal Register preambles (the codified rules above are the binding text).
