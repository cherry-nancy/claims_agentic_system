"""Stratified sample: dev 100 / test 200 (design §10.1). Writes protected files; refuses to overwrite.

    uv run python research/sample.py

Inputs: data/derived/cohort/pool.parquet, data/splits/admissions.csv (frozen), data/derived/parquet/*,
knowledge/needs.yaml. Outputs: data/splits/{dev,test}_cases.csv and data/splits/sample.meta.json.

Rules (step ②; revised after the 2026-11-09 team review, decision_log D-008):
- dev cases only from dev admissions, test cases only from test admissions (admissions.csv, split by hadm_id).
- Cells = scenario x discharge location (no REHAB). Per scenario: dev SNF 8 / HHC 7 / HOME 5 (= 20),
  test twice that (= 40). 5 scenarios -> dev 100, test 200.
- In every cell about 25% of the slots go to boundary cases (observation admission type, < 3 naive
  midnights, or admitted from a SNF); the rest are drawn from all remaining candidates of the cell.
- The unit is the admission: a patient may contribute more than one admission. Cells are filled scarcest-first.
- Shortfall in a cell moves to HHC, then SNF, of the same scenario; recorded in the meta file.
- Order inside a cell = sha256(SALT:hadm_id); deterministic on any machine.
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import defaultdict

import duckdb

from scenarios import SCENARIOS, SPLIT, build_candidates  # noqa: E402  (run from repo root: research/ on path)
from snf_pa.paths import ROOT

SALT = "snf-pa-sample-v2"
DEV_QUOTA = {"SKILLED NURSING FACILITY": 8, "HOME HEALTH CARE": 7, "HOME": 5}
MULT = {"dev": 1, "test": 2}
BOUNDARY_SHARE = 0.25
FALLBACK = ["HOME HEALTH CARE", "SKILLED NURSING FACILITY"]
OUT = ROOT / "data" / "splits"
FILES = {"dev": OUT / "dev_cases.csv", "test": OUT / "test_cases.csv"}
META = OUT / "sample.meta.json"
COLS = ["hadm_id", "subject_id", "split", "scenario", "discharge_location", "boundary", "observation_admit_type",
        "naive_midnights", "from_snf", "hip_fracture", "needs", "slot"]


def rank(hadm_id: int) -> str:
    return hashlib.sha256(f"{SALT}:{hadm_id}".encode()).hexdigest()


def boundary_slots(k: int) -> int:
    return int(k * BOUNDARY_SHARE + 0.5)


def draw(rows: list[dict], split: str) -> tuple[list[dict], list[dict]]:
    by_cell = defaultdict(list)
    for r in rows:
        by_cell[(r["scenario"], r["discharge_location"])].append(r)
    for v in by_cell.values():
        v.sort(key=lambda r: rank(r["hadm_id"]))
    target = {(s, loc): q * MULT[split] for s in SCENARIOS for loc, q in DEV_QUOTA.items()}
    used, picked, cells = set(), [], []
    order = sorted(target, key=lambda c: len(by_cell[c]))  # scarcest cell first

    def take(cell, k, want_boundary):
        out = []
        for r in by_cell[cell]:
            if len(out) == k:
                break
            if r["hadm_id"] in used or (want_boundary and not r["boundary"]):
                continue
            used.add(r["hadm_id"])
            out.append(r)
        return out

    rep = {c: {"cell": c, "target": target[c], "selected": 0, "boundary": 0, "received_from_shortfall": 0,
               "shortfall": 0, "shortfall_moved_to": None} for c in target}

    def fill(cell, k):
        """Fill k slots of a cell (25% boundary first); return how many could not be filled."""
        got_b = take(cell, boundary_slots(k), True)
        got_o = take(cell, k - len(got_b), False)
        for r, slot in [(r, "boundary") for r in got_b] + [(r, "open") for r in got_o]:
            picked.append({**r, "slot": slot})
        rep[cell]["selected"] += len(got_b) + len(got_o)
        rep[cell]["boundary"] += sum(r["boundary"] for r in got_b + got_o)
        return k - len(got_b) - len(got_o)

    # pass 1: every cell's own quota, scarcest cell first
    shortfalls = {}
    for cell in order:
        short = fill(cell, target[cell])
        if short:
            shortfalls[cell] = short
    # pass 2: move each shortfall along the fallback chain of the same scenario
    for cell, short in shortfalls.items():
        rep[cell]["shortfall"] = short
        for loc in [f for f in FALLBACK if f != cell[1]]:
            dst = (cell[0], loc)
            left = fill(dst, short)
            rep[dst]["received_from_shortfall"] += short - left
            rep[cell]["shortfall_moved_to"] = loc
            short = left
            if not short:
                break
        if short:
            raise SystemExit(f"{split}: cannot fill {cell}: {short} slots left after fallback")
    return picked, list(rep.values())


def main() -> None:
    if any(f.exists() for f in FILES.values()) or META.exists():
        sys.exit("sample files already exist; they are protected and are never regenerated.")
    con = duckdb.connect()
    cat = build_candidates(con)
    meta = {"salt": SALT, "dev_quota_per_scenario": DEV_QUOTA, "test_multiplier": 2, "boundary_share": BOUNDARY_SHARE,
            "fallback_order": FALLBACK, "scenarios": list(SCENARIOS),
            "needs_catalog": {"version": cat.version, "hash": cat.content_hash},
            "split_file_sha256": hashlib.sha256(SPLIT.read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
            "splits": {}}
    for split in ("dev", "test"):
        rows = [dict(zip([d[0] for d in con.description], r)) for r in
                con.execute("select * from cand where split = ? and scenario != 'other'", [split]).fetchall()]
        picked, cells = draw(rows, split)
        picked.sort(key=lambda r: r["hadm_id"])
        with FILES[split].open("w", encoding="utf-8", newline="\n") as f:
            f.write(",".join(COLS) + "\n")
            for r in picked:
                vals = [r[c] if c != "needs" else ";".join(r["needs"]) for c in COLS]
                f.write(",".join("" if v is None else str(v) for v in vals) + "\n")
        tags = defaultdict(int)
        for r in picked:
            for n in r["needs"]:
                tags[n] += 1
        meta["splits"][split] = {
            "n": len(picked),
            "cells": [{**c, "cell": list(c["cell"])} for c in cells],
            "need_tag_counts": dict(sorted(tags.items())),
            "hip_fracture": sum(r["hip_fracture"] for r in picked),
            "boundary": sum(r["boundary"] for r in picked),
        }
        print(f"{split}: {len(picked)} cases -> {FILES[split]}")
    META.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
