"""Chunk real policy docs, index in memory (bge-m3 via Ollama, optional) + BM25, compare retrieval modes.

Without a running Ollama the vector and hybrid modes are skipped and only BM25 runs.
"""
import math
import re
import time
from pathlib import Path

from bs4 import BeautifulSoup
from langchain_ollama import OllamaEmbeddings
from pypdf import PdfReader
from rank_bm25 import BM25Okapi

DOCS = Path("policy_docs")
MAX_CHARS = 2400


def split_long(text: str) -> list[str]:
    if len(text) <= MAX_CHARS:
        return [text]
    parts, cur = [], ""
    for para in re.split(r"\n\s*\n|(?<=\.)\s{2,}", text):
        if len(cur) + len(para) > MAX_CHARS and cur:
            parts.append(cur)
            cur = ""
        cur += para + "\n"
    if cur.strip():
        parts.append(cur)
    return parts


def chunk_cfr() -> list[dict]:
    soup = BeautifulSoup((DOCS / "42cfr409_subpartD.xml").read_text(encoding="utf-8"), "html.parser")
    out = []
    for sec in soup.find_all("div8"):
        num = sec.get("n")
        text = re.sub(r"\s+", " ", sec.get_text(" ")).strip()
        for i, t in enumerate(split_long(text)):
            out.append({"text": t, "source": "42 CFR 409", "section": f"{num}" + (f" (part {i+1})" if i else "")})
    return out


HEAD_RE = re.compile(r"^(\d{1,3}(?:\.\d+)*(?:\.[A-Z])?)\s+-\s+(.+)$", re.M)


def chunk_manual() -> list[dict]:
    pages = PdfReader(DOCS / "bp102c08.pdf").pages
    full = "\n".join(p.extract_text() for p in pages)
    start = full.find("10 - Requirements - General", full.find("Transmittals Issued") + 2000)
    body = full[start:] if start > 0 else full
    marks = list(HEAD_RE.finditer(body))
    out = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        text = body[m.start():end].strip()
        if len(text) < 80:
            continue
        for j, t in enumerate(split_long(text)):
            out.append({"text": t, "source": "BPM Ch.8", "section": f"{m.group(1)} {m.group(2)[:50]}" + (f" (part {j+1})" if j else "")})
    return out


def tok(s: str) -> list[str]:
    return re.findall(r"[a-z0-9\.]+", s.lower())


chunks = chunk_cfr() + chunk_manual()
print(f"chunks: {len(chunks)}  (cfr={sum(c['source']=='42 CFR 409' for c in chunks)}, "
      f"manual={sum(c['source']=='BPM Ch.8' for c in chunks)}), "
      f"avg chars={sum(len(c['text']) for c in chunks)//len(chunks)}")

emb = OllamaEmbeddings(model="bge-m3")
t = time.time()
try:
    vecs = []
    for i in range(0, len(chunks), 16):
        vecs += emb.embed_documents([c["text"] for c in chunks[i:i + 16]])
    print(f"embedded in memory in {time.time() - t:.1f}s")
except Exception as e:  # Ollama not running
    vecs = None
    print(f"embeddings unavailable ({type(e).__name__}); running BM25 only")

bm25 = BM25Okapi([tok(c["text"]) for c in chunks])


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b)) / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def vector_rank(q: str, k: int = 10) -> list[int]:
    qv = emb.embed_query(q)
    s = [cosine(qv, v) for v in vecs]
    return sorted(range(len(chunks)), key=lambda i: -s[i])[:k]


def bm25_rank(q: str, k: int = 10) -> list[int]:
    s = bm25.get_scores(tok(q))
    return sorted(range(len(chunks)), key=lambda i: -s[i])[:k]


def hybrid_rank(q: str, k: int = 10) -> list[int]:
    score: dict[int, float] = {}
    for ranking in (vector_rank(q, 20), bm25_rank(q, 20)):
        for r, i in enumerate(ranking):
            score[i] = score.get(i, 0) + 1 / (60 + r)
    return sorted(score, key=score.get, reverse=True)[:k]


# (query, regex that a correct chunk's section/text must match)
QUERIES = [
    ("How many days must a patient be hospitalized before Medicare covers SNF care?", r"3 consecutive|three consecutive"),
    ("Within how many days after hospital discharge must the patient be admitted to the SNF?", r"30 days|30-day"),
    ("What does it mean for skilled services to be needed on a daily basis?", r"daily basis|5 days|7 days"),
    ("When is SNF care considered a practical matter only available in an inpatient facility?", r"practical matter"),
    ("Who must certify that the patient needs skilled nursing facility care?", r"certif"),
    ("409.33 examples of skilled nursing and rehabilitation services", r"409\.33"),
]

modes = {"bm25": bm25_rank} if vecs is None else {"vector": vector_rank, "bm25": bm25_rank, "hybrid": hybrid_rank}
hits = {m: 0 for m in modes}
for q, pat in QUERIES:
    print(f"\nQ: {q}")
    for m, fn in modes.items():
        top = fn(q, 5)
        ok = any(re.search(pat, chunks[i]["section"] + " " + chunks[i]["text"], re.I) for i in top)
        hits[m] += ok
        print(f"  [{m:6}] {'HIT ' if ok else 'MISS'} " + " | ".join(f"{chunks[i]['source'][:3]} {chunks[i]['section'][:34]}" for i in top[:3]))

print("\nrecall@5 (pattern appears in a top-5 chunk):", {m: f"{h}/{len(QUERIES)}" for m, h in hits.items()})
