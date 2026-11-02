"""Paths, seed and quotas for the Step 1 sample."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

# MIMIC location; override with MIMIC_ROOT if the PhysioNet download lives elsewhere.
MIMIC_ROOT = Path(os.environ.get("MIMIC_ROOT", ROOT / "physionet.org" / "files"))
HOSP = MIMIC_ROOT / "mimiciv" / "3.1" / "hosp"
ICU = MIMIC_ROOT / "mimiciv" / "3.1" / "icu"
NOTE = MIMIC_ROOT / "mimic-iv-note" / "2.2" / "note"

SAMPLE_DIR = ROOT / "data" / "sample"

SEED = 42
MIN_AGE = 65
MIN_MIDNIGHTS = 3

CATEGORIES = ["hip_fracture", "stroke", "heart_failure", "pneumonia_sepsis", "joint_replacement"]

# Cases per category, cumulative by batch. Batch 1 is the original 50; batch 2 tops each category up to 60.
QUOTAS = {
    1: {"SKILLED NURSING FACILITY": 5, "HOME HEALTH CARE": 3, "HOME": 2},
    2: {"SKILLED NURSING FACILITY": 30, "HOME HEALTH CARE": 18, "HOME": 12},
}
TEST_FRACTION = 0.4
# Split rule used by sample_cases1.csv and its supplement: rank within a cell by hash; position % 5 in (1, 2) -> test.
TEST_MODULUS = 5
TEST_POSITIONS = (1, 2)


def sql_path(p: Path) -> str:
    return p.as_posix()
