"""Hybrid search over the policy corpus (plan Step 3) and its retrieval evaluation.

Run from the project root (needs Ollama with qwen3-embedding:0.6b and a release built by snf_pa.rag.build):
    PYTHONPATH=src uv run python -m snf_pa.rag.index            # recall@k per mode on the evaluation set
    PYTHONPATH=src uv run python -m snf_pa.rag.index "query"    # top 5 chunks for one query

Two rankings of every chunk, fused:
  bm25    - word match (rank_bm25) over the chunk text; finds exact terms such as "observation" or "§ 409.34".
  vector  - cosine similarity of qwen3-embedding:0.6b embeddings; finds paraphrases ("too frail to travel" ~
            "physical condition"). Queries get the model's instruction prefix (QUERY_PREFIX); chunks get none.
  hybrid  - reciprocal rank fusion of the two: score = sum over rankings of 1 / (RRF_K + rank).
No reranker: bge-reranker-v2-m3 over the hybrid top 20 lowered recall@5 from 0.96 to 0.91 (plan Step 3).
The corpus is small (about 160 chunks), so all chunks are scored for every query and no vector database is
needed. The chunks and their embeddings come from a release (snf_pa.rag.build); loading one checks every chunk's
text hash and that Ollama still serves the embedding model it was built with, and only queries are embedded.

Filters: `max_tier` (2 keeps tier 3, the IRF rule, out of a SNF decision) and `programs`.
The evaluation set is policy_docs/derived/retrieval_eval_GENERATED.yaml (an item may need two rules: expect_all);
the plan's target is recall@5 >= 0.9. Recall is also reported by item kind and author.
"""
import hashlib
import json
import os
import re
import sys

import httpx
import numpy as np
import polars as pl
import yaml
from langchain_ollama import OllamaEmbeddings
from rank_bm25 import BM25Okapi

from snf_pa.data.config import ROOT

# Chosen on the 153-question set (plan Step 3): hybrid recall@5 0.92 vs 0.88 for bge-m3 and embeddinggemma.
EMBED_MODEL = "qwen3-embedding:0.6b"
QUERY_PREFIX = "Instruct: Given a question about Medicare SNF coverage, retrieve the policy passage that answers it\nQuery: "
INDEX = ROOT / "derived" / "rag" / "index"
LATEST = INDEX / "LATEST"
EVAL = ROOT / "policy_docs" / "derived" / "retrieval_eval_GENERATED.yaml"
RRF_K = 60
MODES = ("bm25", "vector", "hybrid")


def words(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:\.[0-9]+)*", s.lower())


def model_digest(model: str = EMBED_MODEL) -> str:
    """The digest of the model Ollama serves under this name."""
    host = os.environ.get("OLLAMA_HOST", "localhost:11434")
    host = host if host.startswith("http") else "http://" + host
    name = model if ":" in model else model + ":latest"
    for m in httpx.get(f"{host}/api/tags", timeout=10).raise_for_status().json()["models"]:
        if m["name"] == name:
            return m["digest"]
    raise RuntimeError(f"Ollama has no {name}; run `ollama pull {model}`")


class PolicyIndex:
    def __init__(self, chunks: list[dict], vectors: np.ndarray, manifest: dict):
        self.chunks, self.manifest = chunks, manifest
        self.embedder = OllamaEmbeddings(model=manifest["embedding"]["model"])
        self.query_prefix = manifest["embedding"].get("query_prefix", "")
        self.bm25 = BM25Okapi([words(c["text"]) for c in chunks])
        self.vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)

    @classmethod
    def load(cls, version: str | None = None) -> "PolicyIndex":
        """A built release (default: the one LATEST names). Fails rather than embedding anything itself."""
        if version is None:
            if not LATEST.exists():
                raise FileNotFoundError(f"no {LATEST}; build a release: python -m snf_pa.rag.build")
            version = LATEST.read_text().strip()
        d = INDEX / version
        manifest = json.loads((d / "manifest.json").read_text())
        emb = manifest["embedding"]
        if (served := model_digest(emb["model"])) != emb["ollama_digest"]:
            raise RuntimeError(f"release {version} was embedded with {emb['model']} {emb['ollama_digest'][:12]}, "
                               f"Ollama now serves {served[:12]}; rebuild: python -m snf_pa.rag.build")
        df = pl.read_parquet(d / "chunks.parquet")
        bad = [r["id"] for r in df.select("id", "text", "text_sha256").to_dicts()
               if hashlib.sha256(r["text"].encode()).hexdigest() != r["text_sha256"]]
        if bad or len(df) != manifest["n_chunks"]:
            raise RuntimeError(f"release {version} is corrupt: {len(bad)} chunk hashes differ, "
                               f"{len(df)} rows vs {manifest['n_chunks']} in the manifest")
        return cls(df.drop("vector", "text_sha256").to_dicts(), df["vector"].to_numpy().astype(np.float32), manifest)

    def rank(self, query: str, mode: str) -> np.ndarray:
        """Chunk indices, best first."""
        if mode == "bm25":
            return np.argsort(-self.bm25.get_scores(words(query)), kind="stable")
        if mode == "vector":
            q = np.asarray(self.embedder.embed_query(self.query_prefix + query), dtype=np.float32)
            return np.argsort(-(self.vectors @ (q / np.linalg.norm(q))), kind="stable")
        fused = np.zeros(len(self.chunks))
        for m in ("bm25", "vector"):
            fused[self.rank(query, m)] += 1 / (RRF_K + np.arange(1, len(self.chunks) + 1))
        return np.argsort(-fused, kind="stable")

    def search(self, query: str, k: int = 5, mode: str = "hybrid", max_tier: int | None = None,
               programs: set[str] | None = None) -> list[dict]:
        out = []
        for i in self.rank(query, mode):
            c = self.chunks[i]
            if (max_tier is None or c["tier"] <= max_tier) and (programs is None or c["program"] in programs):
                out.append(c)
                if len(out) == k:
                    break
        return out


def covers(chunk: dict, citation: str) -> bool:
    """Whether the chunk holds the cited paragraph or a part of it. "=" before a citation means that paragraph's own
    text only, not its sub-paragraphs (e.g. "=BPM Ch.8 §30" is not covered by a chunk of §30.6)."""
    if citation.startswith("="):
        return citation[1:] in chunk["paragraphs"]
    return any(p == citation or (p.startswith(citation) and p[len(citation)] in "(. ") for p in chunk["paragraphs"])


def groups(item: dict) -> list[list[str]]:
    """An evaluation item's expected citations as groups: `expect` is one group; `expect_all` lists several, and a
    hit needs a chunk for every group."""
    return item.get("expect_all") or [item["expect"]]


def hit_rank(top: list[dict], item: dict) -> int | None:
    """Rank at which every group of the item is covered, or None if one is missing from `top`."""
    ranks = []
    for g in groups(item):
        r = next((r for r, c in enumerate(top, 1) if any(covers(c, e) for e in g)), None)
        if r is None:
            return None
        ranks.append(r)
    return max(ranks)


def evaluate(index: PolicyIndex, ks=(1, 3, 5)) -> dict:
    items = yaml.safe_load(EVAL.read_text(encoding="utf-8"))["items"]
    report = {}
    for mode in MODES:
        ranks = []
        for it in items:
            top = index.search(it["question"], k=max(ks), mode=mode)
            ranks.append((it, hit_rank(top, it), top))
        by = {}
        for field in ("kind", "author"):
            for value in sorted({it.get(field, "original") for it in items}):
                hs = [h for it, h, _ in ranks if it.get(field, "original") == value]
                by[f"{field}={value}"] = {"n": len(hs), f"recall@{max(ks)}": sum(h is not None for h in hs) / len(hs)}
        single = [h for it, h, _ in ranks if "expect_all" not in it]
        report[mode] = {"recall": {k: sum(h is not None and h <= k for _, h, _ in ranks) / len(items) for k in ks},
                        # one-rule items only: the build gate (two-rule items depend on snf_pa.rag.decompose)
                        "recall_single": {max(ks): sum(h is not None for h in single) / len(single)},
                        "mrr": sum(1 / h for _, h, _ in ranks if h) / len(items),
                        "by": by,
                        "misses": [(it["id"], it["question"], [c["citation"] for c in top[:3]])
                                   for it, h, top in ranks if h is None]}
    return report


def main() -> None:
    index = PolicyIndex.load()
    if len(sys.argv) > 1:
        for c in index.search(" ".join(sys.argv[1:])):
            print(f"{c['citation']}  [tier {c['tier']}, {c['source_file']}]")
        return
    report = evaluate(index)
    n = len(yaml.safe_load(EVAL.read_text(encoding="utf-8"))["items"])
    print(f"release {index.manifest['version']}: {n} questions, {len(index.chunks)} chunks")
    for mode, r in report.items():
        rec = "  ".join(f"recall@{k} {v:.2f}" for k, v in r["recall"].items())
        print(f"{mode:7s} {rec}  MRR {r['mrr']:.2f}  misses@5 {len(r['misses'])}  "
              f"one-rule recall@5 {r['recall_single'][5]:.2f}")
    for group, r in report["hybrid"]["by"].items():
        print(f"  hybrid {group:20s} n={r['n']:3d}  recall@5 {r['recall@5']:.2f}")
    for qid, q, top in report["hybrid"]["misses"]:
        print(f"  hybrid miss {qid}: {q}\n      top 3: {top}")


if __name__ == "__main__":
    main()
