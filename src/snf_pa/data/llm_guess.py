"""Step 2 leakage check 3: can a local LLM guess the discharge destination from the packet?

Runs only on dev cases, with a local Ollama model (notes never leave the machine). The raw note is
a positive control: if the model cannot find the disposition there, the strict result means nothing.
Every category is 50% SNF, so 0.5 is the diagnosis-only baseline.

Run:  $env:PYTHONPATH="src"; uv run python -m snf_pa.data.llm_guess [n_strict] [n_raw]
Model from env SNF_GUESS_MODEL (default medgemma:4b; qwen3:14b took >5 min per case on this laptop).
Writes data/sample/llm_guess_<model>.parquet (per case, local) and prints aggregates only.
Check the raw positive control first (n_strict=0): if the model cannot pass it, skip the strict run.
"""
import json
import os
import sys
import time

import ollama
import polars as pl
from pydantic import BaseModel, Field
from sklearn.metrics import roc_auc_score

from . import config as C

MODEL = os.environ.get("SNF_GUESS_MODEL", "medgemma:4b")
SEED = 42
PROMPT = """/no_think
Below is a hospital discharge summary for a Medicare patient, possibly with parts removed.
Guess where the patient went after discharge:
  "SNF"  = skilled nursing facility / rehab facility
  "HOME" = home, with or without home health services
Return JSON with "guess" and "p_snf" (your probability, 0 to 1, that it was SNF).

SUMMARY:
{text}"""


class Guess(BaseModel):
    guess: str = Field(pattern="^(SNF|HOME)$")
    p_snf: float = Field(ge=0, le=1)


def packet_text(path, hadm_ids: list[int]) -> dict[int, str]:
    df = (pl.read_parquet(path).filter(pl.col("hadm_id").is_in(hadm_ids)).sort("hadm_id", "start")
          .group_by("hadm_id", maintain_order=True).agg(pl.col("text").str.join("\n")))
    return dict(df.iter_rows())


def ask(text: str) -> Guess | None:
    try:
        r = ollama.chat(model=MODEL, messages=[{"role": "user", "content": PROMPT.format(text=text)}],
                        format=Guess.model_json_schema(),
                        think=False,  # thinking models (gemma4) otherwise spend num_predict on reasoning
                        options={"temperature": 0, "seed": SEED, "num_ctx": 16384, "num_predict": 64})
        return Guess.model_validate_json(r["message"]["content"])
    except Exception:  # noqa: BLE001 - count failures; do not print model output (may echo note text)
        return None


def pick(cases: pl.DataFrame, n: int) -> list[int]:
    """Balanced dev subset: n/2 SNF, n/2 not, spread across categories by hash order."""
    dev = cases.filter(pl.col("split") == "dev").with_columns(pl.col("hadm_id").hash(SEED).alias("h"))
    out = []
    for y in (1, 0):
        g = dev.filter(pl.col("label_snf") == y).sort("h")
        g = g.with_columns(pl.col("h").rank().over("category").alias("r")).sort("r", "category")
        out += g["hadm_id"].head(n // 2).to_list()
    return out


def summarize(rows: list[dict]) -> dict:
    ok = [r for r in rows if r["p_snf"] is not None]
    if not ok:
        return {"n": len(rows), "failed": len(rows)}
    y = [r["label_snf"] for r in ok]
    acc = sum((r["guess"] == "SNF") == bool(r["label_snf"]) for r in ok) / len(ok)
    auc = roc_auc_score(y, [r["p_snf"] for r in ok]) if len(set(y)) == 2 else None
    return {"n": len(rows), "failed": len(rows) - len(ok), "accuracy": round(acc, 3),
            "auc": round(auc, 3) if auc is not None else None,
            "mean_sec_per_case": round(sum(r["sec"] for r in rows) / len(rows), 1)}


def main() -> None:
    n_strict = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    n_raw = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    d = C.SAMPLE_DIR
    cases = pl.read_csv(d / "sample_cases.csv").select("hadm_id", "label_snf", "split", "category")
    lab = dict(cases.select("hadm_id", "label_snf").iter_rows())
    runs = {"strict": (d / "packets_strict.parquet", pick(cases, n_strict)),
            "raw": (d / "spans_all.parquet", pick(cases, n_raw))}
    rows = []
    for packet, (path, ids) in runs.items():
        texts = packet_text(path, ids)
        for i, h in enumerate(ids, 1):
            t0 = time.time()
            g = ask(texts[h])
            rows.append({"packet": packet, "hadm_id": h, "label_snf": lab[h], "guess": g.guess if g else None,
                         "p_snf": g.p_snf if g else None, "sec": round(time.time() - t0, 1)})
            print(f"{packet} {i}/{len(ids)}", flush=True)
    tag = MODEL.replace(":", "_")
    df = pl.DataFrame(rows)
    df.write_parquet(d / f"llm_guess_{tag}.parquet")
    rep = {"model": MODEL, **{p: summarize([r for r in rows if r["packet"] == p]) for p in runs if runs[p][1]}}
    (d / f"llm_guess_report_{tag}.json").write_text(json.dumps(rep, indent=2))
    print(json.dumps(rep, indent=2))


if __name__ == "__main__":
    main()
