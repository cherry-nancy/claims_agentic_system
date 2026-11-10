"""data/splits/{dev,test}_cases.csv: sizes, split discipline (by admission), quotas, determinism."""
import csv
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPLITS = ROOT / "data" / "splits"
FILES = {"dev": SPLITS / "dev_cases.csv", "test": SPLITS / "test_cases.csv"}
META = SPLITS / "sample.meta.json"
PARQUET_READY = (ROOT / "data" / "derived" / "parquet" / "poe.parquet").exists()

pytestmark = pytest.mark.skipif(not all(f.exists() for f in FILES.values()), reason="sample not drawn yet")


def read(split):
    with FILES[split].open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.fixture(scope="module")
def admissions():
    with (SPLITS / "admissions.csv").open(encoding="utf-8") as f:
        return {int(r["hadm_id"]): r["split"] for r in csv.DictReader(f)}


def test_sizes():
    assert len(read("dev")) == 100
    assert len(read("test")) == 200


def test_split_discipline_and_unique_admissions(admissions):
    """Design v9: split and sampling unit is the admission; a patient may appear more than once."""
    seen = set()
    for split in ("dev", "test"):
        for r in read(split):
            h = int(r["hadm_id"])
            assert admissions[h] == split, f"{h} drawn into {split} but belongs to {admissions[h]}"
            assert h not in seen
            seen.add(h)


def test_no_rehab():
    for split in ("dev", "test"):
        assert {r["discharge_location"] for r in read(split)} <= {"SKILLED NURSING FACILITY", "HOME HEALTH CARE", "HOME"}


def test_quota_settings_pinned():
    """Design v9 / step2_plan revision: per scenario dev SNF 8 / HHC 7 / HOME 5, test x2 (20 / 40 per scenario)."""
    meta = json.loads(META.read_text(encoding="utf-8"))
    assert meta["dev_quota_per_scenario"] == {"SKILLED NURSING FACILITY": 8, "HOME HEALTH CARE": 7, "HOME": 5}
    assert meta["test_multiplier"] == 2
    for split, per in (("dev", 20), ("test", 40)):
        rows = read(split)
        for scen in meta["scenarios"]:
            assert sum(r["scenario"] == scen for r in rows) == per, (split, scen)


def test_cells_match_quotas():
    meta = json.loads(META.read_text(encoding="utf-8"))
    for split in ("dev", "test"):
        rows = read(split)
        for c in meta["splits"][split]["cells"]:
            scen, loc = c["cell"]
            n = sum(r["scenario"] == scen and r["discharge_location"] == loc for r in rows)
            assert n == c["selected"] == c["target"] - c["shortfall"] + c["received_from_shortfall"]


@pytest.mark.skipif(not PARQUET_READY, reason="Parquet subset not built on this machine")
def test_redraw_is_identical():
    import duckdb
    sys.path.insert(0, str(ROOT / "research"))
    import sample  # noqa: E402
    import scenarios  # noqa: E402

    con = duckdb.connect()
    scenarios.build_candidates(con)
    for split in ("dev", "test"):
        rows = [dict(zip([d[0] for d in con.description], r)) for r in
                con.execute("select * from cand where split = ? and scenario != 'other'", [split]).fetchall()]
        picked, _ = sample.draw(rows, split)
        assert sorted(int(r["hadm_id"]) for r in picked) == sorted(int(r["hadm_id"]) for r in read(split))
