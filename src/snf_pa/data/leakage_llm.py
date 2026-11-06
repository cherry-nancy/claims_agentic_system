"""LLM leakage check: a local model guesses the destination from a redacted note and quotes its evidence.

Run from the project root (after snf_pa.data.redact; needs Ollama):
    PYTHONPATH=src uv run python -m snf_pa.data.leakage_llm [--n 40] [--mode strict] [--model qwen3.5:9b-q4_K_M]

A correct guess alone does not show a leak: function, cognition and wounds legitimately predict SNF. What matters
is the evidence. Each quote is checked three ways:
  verbatim - found in the note (whitespace ignored); a quote that is not is discounted
  rule     - matches a disposition rule of snf_pa.data.redact, i.e. a phrase the redactor should have removed
  process  - the model itself calls it discharge planning / destination / services rather than a clinical fact
A verbatim quote flagged by rule or process is a leak candidate; those rows are what to read in the dev review.

Dev split only (the test split stays unseen). Writes data/sample/leakage_llm_{mode}.parquet (gitignored; it holds
quotes, i.e. note text, so it stays local) and prints aggregate counts only.
"""
import argparse
import re
import time
from typing import Literal

import polars as pl
from langchain_core.exceptions import OutputParserException
from langchain_ollama import ChatOllama
from pydantic import BaseModel, Field, ValidationError

from snf_pa.data import config as C
from snf_pa.data.redact import FILES, MODES, TRIGGERS, VERSION

NUM_CTX = 16384
MAX_CHARS = 48000  # about 12k tokens of note; longer notes are skipped and counted
DEST = {"SKILLED NURSING FACILITY": "SNF", "REHAB": "IRF", "HOME HEALTH CARE": "home_health", "HOME": "home"}

PROMPT = """You are auditing a de-identified hospital discharge summary. Text that states where the patient went
after discharge has been removed. Guess the discharge destination anyway, from what is left:
  SNF          skilled nursing facility
  IRF          inpatient rehabilitation facility
  home_health  home with home health services
  home         home without services
Then quote up to 3 short passages (copied exactly from the note, at most 25 words each) that most influenced the
guess. For each quote say whether it is:
  clinical - a clinical or functional fact (diagnosis, procedure, mobility, cognition, wounds, medications, ...)
  process  - discharge planning, a destination, post-discharge services or follow-up arrangements

NOTE:
{note}"""


class Quote(BaseModel):
    text: str = Field(description="passage copied exactly from the note")
    kind: Literal["clinical", "process"]


class Guess(BaseModel):
    destination: Literal["SNF", "IRF", "home_health", "home"]
    confidence: float = Field(ge=0, le=1)
    evidence: list[Quote] = Field(max_length=3)


def squash(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=0, help="cases to run (0 = all dev cases)")
    ap.add_argument("--mode", choices=list(MODES), default="strict")
    ap.add_argument("--model", default="qwen3.5:9b-q4_K_M")
    args = ap.parse_args()

    cases = pl.concat([pl.read_csv(C.SAMPLE_DIR / f"{f}.csv", infer_schema_length=0)
                       .select("hadm_id", "discharge_location", "split") for f in ["sample_cases1", "sample_cases1_supp"]])
    notes = pl.concat([pl.read_parquet(C.SAMPLE_DIR / f"{f}.parquet") for f in FILES.values()])
    assert (notes["redaction_version"] == VERSION).all(), "rerun snf_pa.data.redact first"
    d = (notes.filter(pl.col("mode") == args.mode).with_columns(pl.col("hadm_id").cast(pl.String))
         .join(cases, on="hadm_id").filter(pl.col("split") == "dev").sort("hadm_id"))
    if args.n:  # seeded hash order, so a smaller --n is a prefix of a larger one
        d = d.with_columns(k=pl.col("hadm_id").hash(C.SEED)).sort("k").head(args.n)
    llm = ChatOllama(model=args.model, num_ctx=NUM_CTX, temperature=0, reasoning=False).with_structured_output(Guess)

    rows, skipped, failed, t0 = [], 0, 0, time.time()
    for r in d.iter_rows(named=True):
        if len(r["text"]) > MAX_CHARS:
            skipped += 1
            continue
        try:
            g = llm.invoke(PROMPT.format(note=r["text"]))
        except (OutputParserException, ValidationError, ValueError):  # malformed output; counted, not retried
            failed += 1
            continue
        note = squash(r["text"])
        for q in g.evidence or [Quote(text="", kind="clinical")]:
            rows.append({"hadm_id": r["hadm_id"], "truth": DEST[r["discharge_location"]], "guess": g.destination,
                         "confidence": g.confidence, "quote": q.text, "kind": q.kind,
                         "verbatim": bool(q.text) and squash(q.text) in note,
                         "rule": [k for k, rx in TRIGGERS.items() if rx.search(q.text)]})
        print(f"\r{len({x['hadm_id'] for x in rows})}/{d.height} cases, {time.time() - t0:.0f}s", end="", flush=True)
    print()
    out = pl.DataFrame(rows).with_columns(
        leak_candidate=pl.col("verbatim") & ((pl.col("kind") == "process") | (pl.col("rule").list.len() > 0)))
    out.write_parquet(C.SAMPLE_DIR / f"leakage_llm_{args.mode}.parquet")

    per_case = out.group_by("hadm_id").agg(pl.col("truth", "guess").first(), pl.col("leak_candidate").any())
    quotes = out.filter(pl.col("quote") != "")
    print(f"{args.model}, {args.mode} notes, {per_case.height} dev cases ({skipped} too long, {failed} failed)")
    print(f"accuracy {(per_case['truth'] == per_case['guess']).mean():.2f}; "
          f"majority-class rate {per_case['truth'].value_counts()['count'].max() / per_case.height:.2f}")
    print(f"quotes: {quotes.height}; verbatim {quotes['verbatim'].mean():.2f}; "
          f"self-labelled process {(quotes['kind'] == 'process').mean():.2f}; "
          f"matching a redaction rule {(quotes['rule'].list.len() > 0).mean():.2f}")
    print(f"cases with a leak candidate: {per_case['leak_candidate'].sum()} "
          f"(read these in the dev review: data/sample/leakage_llm_{args.mode}.parquet)")
    print(per_case.group_by("truth", "guess").len().sort("truth", "guess"))


if __name__ == "__main__":
    main()
