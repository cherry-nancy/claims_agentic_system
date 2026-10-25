"""Minimal LangGraph + Ollama pipeline check (no medical accuracy claims)."""
import json
import time
from pathlib import Path
from typing import Optional, TypedDict

from langchain_ollama import ChatOllama
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

TRACE = Path("traces/check_langgraph.jsonl")


class Evidence(BaseModel):
    has_skilled_need: bool
    reason: str


class State(TypedDict, total=False):
    note: str
    inpatient_midnights: int
    eligible: bool
    evidence: Optional[dict]
    decision: str


llm = ChatOllama(model="medgemma:4b", temperature=0)


def trace(node: str, inp: dict, out: dict) -> None:
    TRACE.parent.mkdir(exist_ok=True)
    with TRACE.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"node": node, "in": inp, "out": out}) + "\n")


def eligibility(state: State) -> State:
    # deterministic rule, no LLM
    out = {"eligible": state["inpatient_midnights"] >= 3}
    trace("eligibility", {"midnights": state["inpatient_midnights"]}, out)
    return out


def evidence(state: State) -> State:
    res = llm.with_structured_output(Evidence).invoke(
        f"Does this patient need daily skilled rehab? Note: {state['note']}"
    )
    out = {"evidence": res.model_dump()}
    trace("evidence", {"note": state["note"]}, out)
    return out


def decide(state: State) -> State:
    d = "pend_for_review" if state["evidence"]["has_skilled_need"] else "deny_review"
    trace("decide", {"evidence": state["evidence"]}, {"decision": d})
    return {"decision": d}


def not_eligible(state: State) -> State:
    trace("not_eligible", {}, {"decision": "not_applicable"})
    return {"decision": "not_applicable"}


g = StateGraph(State)
g.add_node("eligibility", eligibility)
g.add_node("evidence", evidence)
g.add_node("decide", decide)
g.add_node("not_eligible", not_eligible)
g.add_edge(START, "eligibility")
g.add_conditional_edges(
    "eligibility", lambda s: "evidence" if s["eligible"] else "not_eligible"
)
g.add_edge("evidence", "decide")
g.add_edge("decide", END)
g.add_edge("not_eligible", END)
app = g.compile()

NOTE = (
    "82F s/p right hip fracture ORIF, POD2. Requires 2-person assist to transfer, "
    "unable to ambulate more than 5 feet. Daily PT/OT needed. Lives alone."
)

TRACE.unlink(missing_ok=True)

t = time.time()
r1 = app.invoke({"note": NOTE, "inpatient_midnights": 4})
print("4 midnights ->", r1["decision"], r1["evidence"], f"({time.time() - t:.1f}s)")
assert r1["decision"] in {"pend_for_review", "deny_review"}
assert isinstance(r1["evidence"]["has_skilled_need"], bool)

t = time.time()
r2 = app.invoke({"note": NOTE, "inpatient_midnights": 1})
print("1 midnight  ->", r2["decision"], r2.get("evidence"), f"({time.time() - t:.1f}s)")
assert r2["decision"] == "not_applicable" and r2.get("evidence") is None

nodes = [json.loads(line)["node"] for line in TRACE.read_text().splitlines()]
print("trace nodes:", nodes)
assert nodes == ["eligibility", "evidence", "decide", "eligibility", "not_eligible"]
print("ALL CHECKS PASSED")
