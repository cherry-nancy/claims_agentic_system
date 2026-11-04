"""Step 2 entry point: raw notes -> sentence spans -> strict / realistic packets + redaction log.

Run:  $env:PYTHONPATH="src"; uv run python -m snf_pa.data.build_packets
Prints aggregate counts only; never prints note text.
"""
import json
from collections import Counter

import polars as pl

from . import config as C
from .redact import index_note, redact

PACKET_SCHEMA = {"note_id": pl.Utf8, "hadm_id": pl.Int64, "span_id": pl.Utf8, "section": pl.Utf8,
                 "start": pl.Int64, "end": pl.Int64, "text": pl.Utf8}


def load_notes() -> pl.DataFrame:
    notes = pl.read_parquet(C.SAMPLE_DIR / "notes_raw.parquet")
    cases = pl.read_csv(C.SAMPLE_DIR / "sample_cases.csv").select("hadm_id", "label_snf", "split", "category")
    return notes.join(cases, on="hadm_id", how="inner")


def build(notes: pl.DataFrame) -> tuple[dict[str, pl.DataFrame], pl.DataFrame, dict]:
    rows = {"all": [], "strict": [], "realistic": []}
    logs = []
    sec_cover = Counter()
    for r in notes.iter_rows(named=True):
        spans = index_note(r["text"])
        sec_cover.update({s.section for s in spans})
        base = {"note_id": r["note_id"], "hadm_id": r["hadm_id"]}
        rows["all"] += [base | {"span_id": s.span_id, "section": s.section, "start": s.start, "end": s.end,
                                "text": s.text} for s in spans]
        for packet in ("strict", "realistic"):
            kept, log = redact(spans, packet)
            rows[packet] += [base | {"span_id": s.span_id, "section": s.section, "start": s.start, "end": s.end,
                                     "text": s.text} for s in kept]
            logs += [base | {"packet": packet, "label_snf": r["label_snf"], "split": r["split"]} | x for x in log]
    frames = {k: pl.DataFrame(v, schema=PACKET_SCHEMA) for k, v in rows.items()}
    log_df = pl.DataFrame(logs)
    report = {"n_notes": notes.height, "notes_with_section": dict(sorted(sec_cover.items()))}
    return frames, log_df, report


def summarize_log(log_df: pl.DataFrame) -> dict:
    """Changes per note, by packet, rule and label (sentence/clause scope only)."""
    agg = (log_df.filter(pl.col("scope") != "section")
           .group_by("packet", "rule", "label_snf").agg(pl.len().alias("n"))
           .sort("packet", "rule", "label_snf"))
    return {f"{r['packet']}|{r['rule']}|snf={r['label_snf']}": r["n"] for r in agg.iter_rows(named=True)}


def main() -> None:
    notes = load_notes()
    frames, log_df, report = build(notes)
    out = C.SAMPLE_DIR
    frames["all"].write_parquet(out / "spans_all.parquet")
    frames["strict"].write_parquet(out / "packets_strict.parquet")
    frames["realistic"].write_parquet(out / "packets_realistic.parquet")
    log_df.write_parquet(out / "redaction_log.parquet")
    report["spans_all"] = frames["all"].height
    report["spans_strict"] = frames["strict"].height
    report["spans_realistic"] = frames["realistic"].height
    report["redactions"] = summarize_log(log_df)
    (out / "step2_build_report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
