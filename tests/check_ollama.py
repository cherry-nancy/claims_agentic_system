import time

from langchain_ollama import ChatOllama, OllamaEmbeddings
from pydantic import BaseModel


class Finding(BaseModel):
    has_skilled_need: bool
    reason: str


NOTE = (
    "82F s/p right hip fracture ORIF, POD2. Requires 2-person assist to transfer, "
    "unable to ambulate more than 5 feet. Daily PT/OT needed. Lives alone."
)

llm = ChatOllama(model="medgemma:4b", temperature=0)
t = time.time()
out = llm.with_structured_output(Finding).invoke(
    f"Does this patient need daily skilled rehab? Note: {NOTE}"
)
print("structured:", out, f"({time.time() - t:.1f}s)")

emb = OllamaEmbeddings(model="bge-m3")
docs = [
    "A beneficiary must have a prior inpatient stay of at least 3 consecutive days.",
    "Skilled nursing facility care must be needed on a daily basis.",
    "Hospice election requires a terminal illness certification.",
]
t = time.time()
dv = emb.embed_documents(docs)
qv = emb.embed_query("how many hospital days are required before SNF admission?")
print("embed dim:", len(qv), f"({time.time() - t:.1f}s)")
scores = [sum(a * b for a, b in zip(qv, d)) for d in dv]
best = max(range(len(docs)), key=scores.__getitem__)
print("top hit:", docs[best])
