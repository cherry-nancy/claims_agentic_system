"""Search one query per policy rule a question needs, then merge (plan Step 3).

Run from the project root (needs Ollama with the LLM and the embedding model, and a release built by
snf_pa.rag.build):
    PYTHONPATH=src uv run python -m snf_pa.rag.decompose              # hybrid vs split on the evaluation set
    PYTHONPATH=src uv run python -m snf_pa.rag.decompose "question"   # the queries and top 5 chunks

Result on the 171-question set (2026-11-08): recall@5 0.87 -> 0.90, two-rule questions 0.46 -> 0.62; the LLM split
23 of 24 two-rule questions and 9 of the other 147 (8 questions fixed, 3 broken). PolicyIndex.search is unchanged;
callers that pass free-text questions use splitter() + search_split().

A question about one patient often needs several rules (qualifying stay, daily skilled need, practical matter).
One hybrid search ranks the best-matching rule first and fills the rest of the top k with chunks on the same
topic, so the second rule is pushed out. Here a local LLM lists the rules as separate queries; each is searched
with hybrid and the result lists are interleaved (first of each, then second of each, ...) without duplicates.

The LLM is not forced to split: a question that needs one rule comes back as itself, and a failed or malformed
answer falls back to the original question. For the evaluation, the LLM's queries are kept in
derived/rag/decompositions.json (keyed by model and question) so a rerun scores the same queries.
"""
import json
import sys
from itertools import zip_longest
from typing import Literal

import yaml
from langchain_core.exceptions import OutputParserException
from langchain_ollama import ChatOllama
from pydantic import BaseModel, Field, ValidationError

from snf_pa.data.config import ROOT
from snf_pa.rag.index import EVAL, PolicyIndex, hit_rank

LLM = "qwen3.5:9b-q4_K_M"
PROMPT_VERSION = "rules-v1"  # part of the key of saved queries, so a prompt change is re-run
MAX_QUERIES = 3
SAVED = ROOT / "derived" / "rag" / "decompositions.json"

# The rules offered to the LLM are the plan's criteria checklist (Step 3), not wording from the evaluation set.
RULES = ("qualifying 3-day hospital stay", "30-day transfer", "condition treated in the hospital",
         "skilled nursing or skilled rehabilitation service", "daily basis", "practical matter",
         "physician certification", "benefit period and benefit days", "level of care presumption",
         "documentation", "MA coverage criteria", "MA prior authorization", "MA organization determination",
         "MA expedited determination", "MA fast-track appeal of a termination", "other")

PROMPT = """A reviewer asks a question about Medicare skilled nursing facility (SNF) coverage or Medicare Advantage
rules. List the separate rules the question asks about, at most {n}, choosing each from:
{rules}
For each rule write a short search question about only that rule, using the patient's facts from the question.
Do not add rules the question does not ask about. If it asks about one rule, list one. If you are not sure,
list one item with rule "other" and the question itself.

QUESTION: {question}"""


class Rule(BaseModel):
    rule: Literal[RULES]
    query: str


class Split(BaseModel):
    rules: list[Rule] = Field(min_length=1, max_length=MAX_QUERIES)


def splitter(model: str = LLM):
    """question -> search queries. The LLM's queries are used only when it finds two or more rules; otherwise, or
    on any failure, the original question is searched as it is, so a one-rule question cannot drift."""
    llm = ChatOllama(model=model, temperature=0, reasoning=False).with_structured_output(Split)

    def split(question: str) -> list[str]:
        try:
            rules = llm.invoke(PROMPT.format(n=MAX_QUERIES, rules=", ".join(RULES), question=question)).rules
        except (OutputParserException, ValidationError, ValueError):
            return [question]
        queries = [f"{r.rule}: {r.query.strip()}" for r in rules if r.query.strip()]
        return queries if len(queries) > 1 else [question]

    return split


def search_split(index: PolicyIndex, queries: list[str], k: int = 5, mode: str = "hybrid", **filters) -> list[dict]:
    """Top k for each query, interleaved without duplicates, cut to k."""
    lists = [index.search(q, k=k, mode=mode, **filters) for q in queries]
    out, seen = [], set()
    for row in zip_longest(*lists):
        for c in row:
            if c is not None and c["id"] not in seen:
                seen.add(c["id"])
                out.append(c)
    return out[:k]


def main() -> None:
    index, split = PolicyIndex.load(), splitter()
    if len(sys.argv) > 1:
        queries = split(" ".join(sys.argv[1:]))
        print("queries:", queries)
        for c in search_split(index, queries):
            print(f"{c['citation']}  [tier {c['tier']}, {c['source_file']}]")
        return

    items = yaml.safe_load(EVAL.read_text(encoding="utf-8"))["items"]
    saved = json.loads(SAVED.read_text()) if SAVED.exists() else {}
    for n, it in enumerate(items, 1):
        key = f"{LLM}|{PROMPT_VERSION}|{it['question']}"
        if key not in saved:
            saved[key] = split(it["question"])
        print(f"\r{n}/{len(items)} questions split", end="", file=sys.stderr, flush=True)
    print(file=sys.stderr)
    SAVED.parent.mkdir(parents=True, exist_ok=True)
    SAVED.write_text(json.dumps(saved, indent=1, ensure_ascii=False) + "\n")

    rows = {"hybrid": {}, "split": {}}
    for it in items:
        rows["hybrid"][it["id"]] = hit_rank(index.search(it["question"], k=5), it)
        rows["split"][it["id"]] = hit_rank(search_split(index, saved[f"{LLM}|{PROMPT_VERSION}|{it['question']}"]), it)
    n_split = sum(len(saved[f"{LLM}|{PROMPT_VERSION}|{it['question']}"]) > 1 for it in items)
    print(f"{len(items)} questions; the LLM split {n_split} of them "
          f"({sum(len(saved[f'{LLM}|{PROMPT_VERSION}|{it['question']}']) > 1 for it in items if it.get('kind') == 'multi')} "
          f"of {sum(it.get('kind') == 'multi' for it in items)} two-rule questions)")
    for mode, hit in rows.items():
        r = {k: sum(h is not None and h <= k for h in hit.values()) / len(items) for k in (1, 3, 5)}
        mrr = sum(1 / h for h in hit.values() if h) / len(items)
        kinds = {}
        for it in items:
            kinds.setdefault(it.get("kind", "original"), []).append(hit[it["id"]] is not None)
        by = "  ".join(f"{k} {sum(v) / len(v):.2f}" for k, v in sorted(kinds.items()))
        print(f"{mode:6s} recall@1 {r[1]:.2f}  recall@3 {r[3]:.2f}  recall@5 {r[5]:.2f}  MRR {mrr:.2f} | {by}")
    gained = sorted(q for q in rows["split"] if rows["split"][q] and not rows["hybrid"][q])
    lost = sorted(q for q in rows["split"] if rows["hybrid"][q] and not rows["split"][q])
    print(f"split fixes {gained}\nsplit breaks {lost}")


if __name__ == "__main__":
    main()
