"""Paths and sampling design for the Step 1 cohort."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data"
HOSP = DATA / "mimiciv-3.1" / "hosp"
ICU = DATA / "mimiciv-3.1" / "icu"
NOTE_FILE =DATA / "mimic-iv-note" / "note" / "discharge.csv.gz"
SAMPLE_DIR = DATA / "sample"  # gitignored with the rest of data/

SEED = 42
MIN_AGE = 65
MIN_MIDNIGHTS = 3  # Medicare qualifying inpatient stay

CATEGORIES = ["hip_fracture", "stroke", "heart_failure", "pneumonia_sepsis", "joint_replacement"]

# Target cases per (category, discharge_location): 60 per category, 300 in total.
# SNF is the positive label; HOME HEALTH CARE and HOME are the (hard) negatives.
LOCATION_QUOTAS = {
    "SKILLED NURSING FACILITY": 30,
    "HOME HEALTH CARE": 18,
    "HOME": 12,
}
# If a cell has too few eligible patients, its shortfall moves to the next negative cell
# (HOME -> HOME HEALTH CARE) so every category still gets 60 cases and 50% positives.
NEGATIVE_FALLBACK = {"HOME": "HOME HEALTH CARE"}

# The first 50-case sample (batch 1) is the prefix of every cell's ranking; later cases are batch 2.
BATCH1_QUOTAS = {"SKILLED NURSING FACILITY": 5, "HOME HEALTH CARE": 3, "HOME": 2}

# Within each cell, cases are ranked by hash; position % 5 in TEST_POSITIONS -> test split (40%).
TEST_MODULUS = 5
TEST_POSITIONS = (1, 2)


def sql_path(p: Path) -> str:
    return p.as_posix()
