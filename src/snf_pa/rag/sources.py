"""Registry of the official policy files in policy_docs/: version, program and tier for each.

Every chunk carries these fields, so retrieval can filter (e.g. tier 3 only as background) and every citation
names the file and its version.

Tiers follow the plan (Step 3): 1 = binding rule, 2 = CMS guidance, 3 = background, never a basis for a SNF
decision.
"""
from snf_pa.data.config import ROOT

DOCS = ROOT / "policy_docs"

# file -> metadata. eCFR versions are the "up to date as of" date of the download.
CFR = {
    "42cfr409_subpartD.xml": {
        "version": "eCFR, Title 42 up to date as of 2026-10-30 (file is undated; text verified identical to the "
                   "eCFR download of that date on 2026-11-03)",
        "program": "SNF", "tier": 1,
    },
    "42cfr409_60_ecfr_2026-10-30.xml": {"version": "eCFR, Title 42 up to date as of 2026-10-30",
                                        "program": "benefit_period", "tier": 1},
    "42cfr409_61_ecfr_2026-10-29.xml": {"version": "eCFR, Title 42 up to date as of 2026-10-29",
                                        "program": "benefit_period", "tier": 1},
    "42cfr424_20_ecfr_2026-10-29.xml": {"version": "eCFR, Title 42 up to date as of 2026-10-29",
                                        "program": "SNF", "tier": 1},
    "42cfr422_101_ecfr_2026-10-30.xml": {"version": "eCFR, Title 42 up to date as of 2026-10-30",
                                         "program": "MA", "tier": 1},
    "42cfr422_112_ecfr_2026-10-30.xml": {"version": "eCFR, Title 42 up to date as of 2026-10-30",
                                         "program": "MA", "tier": 1},
    "42cfr422_138_ecfr_2026-10-30.xml": {"version": "eCFR, Title 42 up to date as of 2026-10-30",
                                         "program": "MA", "tier": 1},
    "42cfr422_566_ecfr_2026-10-30.xml": {"version": "eCFR, Title 42 up to date as of 2026-10-30",
                                         "program": "MA", "tier": 1},
    "42cfr422_568_ecfr_2026-10-30.xml": {"version": "eCFR, Title 42 up to date as of 2026-10-30",
                                         "program": "MA", "tier": 1},
    "42cfr422_572_ecfr_2026-10-30.xml": {"version": "eCFR, Title 42 up to date as of 2026-10-30",
                                         "program": "MA", "tier": 1},
    "42cfr422_626_ecfr_2026-10-30.xml": {"version": "eCFR, Title 42 up to date as of 2026-10-30",
                                         "program": "MA", "tier": 1},
    "42cfr412_622_ecfr_2026-10-29.xml": {"version": "eCFR, Title 42 up to date as of 2026-10-29",
                                         "program": "IRF", "tier": 3},
}
