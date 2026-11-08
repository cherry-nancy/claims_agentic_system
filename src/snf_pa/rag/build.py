"""Build a versioned release of the policy RAG index (plan Step 3) in derived/rag/index/<version>/.

Run from the project root (needs Ollama with the embedding model in snf_pa.rag.index):
    PYTHONPATH=src uv run python -m snf_pa.rag.build

A release is what the query side loads (snf_pa.rag.index.PolicyIndex.load); the query side never embeds chunks.
  chunks.parquet  - one row per chunk: the corpus fields (snf_pa.rag.cfr.Chunk), text_sha256 and the vector.
  manifest.json   - embedding model, its Ollama digest and dimension; each source file with its sha256 and
                    version; chunk count, git commit, build time.
  eval.json       - recall@k and MRR per mode on the evaluation set, with the evaluation file's sha256.
The version is the build date plus a hash of the model digest and every chunk's text, so the same inputs give the
same version. derived/rag/index/LATEST names the release to load. It moves only if hybrid recall@5 on the one-rule
questions meets the plan's target; otherwise the build exits with status 1 and LATEST stays where it was. Two-rule
questions (expect_all) are reported but not gated: they rely on splitting the question (snf_pa.rag.decompose),
which needs an LLM and is not run here.
"""
import hashlib
import json
import subprocess
import sys
from dataclasses import asdict
from datetime import UTC, datetime

import numpy as np
import polars as pl
from langchain_ollama import OllamaEmbeddings

from snf_pa.data.config import ROOT
from snf_pa.rag import corpus
from snf_pa.rag.index import (
    EMBED_MODEL,
    EVAL,
    INDEX,
    LATEST,
    QUERY_PREFIX,
    PolicyIndex,
    evaluate,
    model_digest,
)
from snf_pa.rag.sources import CFR, DOCS, PDF

TARGET_RECALL_AT_5 = 0.9


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def git_commit() -> str:
    head = subprocess.run(["git", "rev-parse", "HEAD"], check=True, cwd=ROOT, capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "src/snf_pa/rag", "policy_docs"], check=True,
                           cwd=ROOT, capture_output=True, text=True).stdout.strip()
    return head + ("-dirty" if dirty else "")


def main() -> None:
    chunks, warnings = corpus.build()
    for w in warnings:
        print("WARNING", w)
    digest = model_digest()
    texts = [c.text for c in chunks]
    print(f"embedding {len(texts)} chunks with {EMBED_MODEL}...", file=sys.stderr)
    vectors = np.asarray(OllamaEmbeddings(model=EMBED_MODEL).embed_documents(texts), dtype=np.float32)
    content = sha256("\n".join([digest] + [sha256(t.encode()) for t in texts]).encode())
    now = datetime.now(UTC)
    version = f"{now:%Y%m%d}-{content[:8]}"
    out = INDEX / version
    out.mkdir(parents=True, exist_ok=True)

    rows = [asdict(c) | {"text_sha256": sha256(c.text.encode())} for c in chunks]
    (pl.DataFrame(rows)
     .with_columns(pl.Series("vector", vectors.tolist()).cast(pl.Array(pl.Float32, vectors.shape[1])))
     .write_parquet(out / "chunks.parquet"))
    manifest = {
        "version": version,
        "built_at": now.isoformat(timespec="seconds"),
        "git_commit": git_commit(),
        "embedding": {"model": EMBED_MODEL, "ollama_digest": digest, "dim": int(vectors.shape[1]),
                      "query_prefix": QUERY_PREFIX},
        "sources": [{"file": f"policy_docs/{name}", "sha256": sha256((DOCS / name).read_bytes()),
                     "version": meta["version"], "program": meta["program"], "tier": meta["tier"]}
                    for name, meta in (CFR | PDF).items()],
        "n_chunks": len(chunks),
        "warnings": warnings,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")

    index = PolicyIndex.load(version)
    report = evaluate(index)
    (out / "eval.json").write_text(json.dumps(
        {"eval_file": str(EVAL.relative_to(ROOT)), "eval_sha256": sha256(EVAL.read_bytes()), "modes": report},
        indent=2, ensure_ascii=False) + "\n")
    print(f"release {version}: {len(chunks)} chunks -> {out.relative_to(ROOT)}")
    for mode, r in report.items():
        rec = "  ".join(f"recall@{k} {v:.2f}" for k, v in r["recall"].items())
        print(f"{mode:7s} {rec}  MRR {r['mrr']:.2f}  misses@5 {len(r['misses'])}  "
              f"one-rule recall@5 {r['recall_single'][5]:.2f}")

    if report["hybrid"]["recall_single"][5] < TARGET_RECALL_AT_5:
        print(f"hybrid recall@5 on one-rule questions below {TARGET_RECALL_AT_5}; LATEST not moved", file=sys.stderr)
        sys.exit(1)
    LATEST.write_text(version + "\n")
    print(f"LATEST -> {version}")


if __name__ == "__main__":
    main()
