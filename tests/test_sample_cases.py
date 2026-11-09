"""data/splits/{dev,test}_cases.csv: sizes, split discipline, one admission per patient, quotas, determinism."""
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
def subjects():
    with (SPLITS / "subjects.csv").open(encoding="utf-8") as f:
        return {int(r["subject_id"]): r["split"] for r in csv.DictReader(f)}


def test_sizes():
    assert len(read("dev")) == 100
    assert len(read("test")) == 200


def test_split_discipline_and_unique_patients(subjects):
    seen = set()
    for split in ("dev", "test"):
        for r in read(split):
            sid = int(r["subject_id"])
            assert subjects[sid] == split, f"{sid} drawn into {split} but belongs to {subjects[sid]}"
            assert sid not in seen
            seen.add(sid)


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
