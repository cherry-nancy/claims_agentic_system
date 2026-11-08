"""The policy corpus for the RAG index: CFR sections, BPM Chapter 8 and the CMS-4201-F FAQ, as one list of chunks.

Run from the project root:
    PYTHONPATH=src uv run python -m snf_pa.rag.corpus

Writes derived/rag/policy_chunks.jsonl (gitignored; rebuilt from policy_docs/).
"""
import json
from dataclasses import asdict

from snf_pa.data.config import ROOT
from snf_pa.rag import bpm, cfr, faq
from snf_pa.rag.cfr import Chunk

OUT = ROOT / "derived" / "rag" / "policy_chunks.jsonl"


def build() -> tuple[list[Chunk], list[str]]:
    chunks, warnings = [], []
    for mod in (cfr, bpm, faq):
        c, w = mod.build()
        chunks += c
        warnings += w
    return chunks, warnings


def load() -> list[dict]:
    """The chunks written by main(), as dicts."""
    return [json.loads(line) for line in OUT.read_text(encoding="utf-8").splitlines()]


def main() -> None:
    chunks, warnings = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(asdict(c), ensure_ascii=False) + "\n")
    by = {}
    for c in chunks:
        by.setdefault(c.source_file.removeprefix("policy_docs/"), []).append(c.n_tokens)
    for name, sizes in by.items():
        print(f"{name:52s} {len(sizes):3d} chunks, median {sorted(sizes)[len(sizes) // 2]} tokens")
    print(f"{len(chunks)} chunks -> {OUT.relative_to(ROOT)}")
    for w in warnings:
        print("WARNING", w)


if __name__ == "__main__":
    main()
