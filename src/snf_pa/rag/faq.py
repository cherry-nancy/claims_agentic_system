"""Chunks of the CMS HPMS memo "FAQs related to Coverage Criteria and Utilization Management Requirements in
CMS Final Rule (CMS-4201-F)" (2024-02-06) for the policy RAG index.

Run from the project root:
    PYTHONPATH=src uv run python -m snf_pa.rag.faq

The memo is an introduction and numbered items "N. Question: ... Answer: ...". Each item is a chunk; a long
answer is split between paragraphs and every part keeps the question in its header. Footnotes, which the PDF
puts at the bottom of their page in the middle of an answer, are cut out of the text and become chunks of their
own, as in snf_pa.rag.cfr. A footnote is recognised by its number: a line that starts with the next footnote
number, then everything to the end of that page.
"""
import re

from pypdf import PdfReader

from snf_pa.rag.bpm import paragraphs, split_paras
from snf_pa.rag.cfr import Chunk, tokens
from snf_pa.rag.sources import DOCS, PDF

NAME = "cms_hpms_faq_coverage_criteria_um_2024-02-06.pdf"
CITE = "CMS HPMS FAQ 2024-02-06"
TITLE = "FAQs on Coverage Criteria and Utilization Management Requirements in CMS-4201-F"
ITEM = re.compile(r"(?m)^[ \t]*(\d{1,2})\.[ \t]+Question:[ \t]*")


def split_footnotes(pages: list[str]) -> tuple[str, list[str]]:
    """Page texts -> (body text without footnotes or page numbers, footnotes in order)."""
    body, notes = [], []
    for page in pages:
        keep, in_note = [], False
        for line in page.split("\n"):
            m = re.match(r"[ \t]*(\d{1,2}) (?=\S)", line)
            if m and int(m[1]) == len(notes) + 1:
                notes.append(line[m.end():])
                in_note = True
            elif in_note:  # a footnote runs to the end of its page
                notes[-1] += "\n" + line
            elif not re.fullmatch(r"[ \t]*\d{1,3}[ \t]*", line):  # a page number
                keep.append(line)
        body.append("\n".join(keep))
    return "\n".join(body), [re.sub(r"\s+", " ", n).strip() for n in notes]


def build() -> tuple[list[Chunk], list[str]]:
    pages = [p.extract_text() for p in PdfReader(DOCS / NAME).pages]
    text, notes = split_footnotes(pages)
    items = list(ITEM.finditer(text))
    warnings = [] if [int(m[1]) for m in items] == list(range(1, len(items) + 1)) else ["questions out of order"]
    meta, chunks = PDF[NAME], []

    def add(cit: str, section: str, title: str, header: str, body: str) -> None:
        chunks.append(Chunk(cit, cit, section, title, [cit], header, body, header + "\n\n" + body,
                            tokens(header + "\n\n" + body), f"policy_docs/{NAME}", meta["version"], meta["program"],
                            meta["tier"], ""))

    head = f"{CITE} {TITLE}"
    intro = text[:items[0].start()] if items else text
    for h, g in split_paras(paragraphs(intro), head, head + " (introduction, continued)"):
        add(f"{CITE} introduction", "introduction", "Introduction", h, "\n\n".join(g))
    for k, m in enumerate(items):
        end = items[k + 1].start() if k + 1 < len(items) else len(text)
        item = text[m.start():end]
        question = re.sub(r"\s+", " ", item[m.end() - m.start():item.find("Answer:")]).strip()
        parts = split_paras(paragraphs(item), head, f"{head}\nQ{m[1]} (continued): {question}")
        for j, (h, g) in enumerate(parts):
            cit = f"{CITE} Q{m[1]}" + (f" (part {j + 1})" if len(parts) > 1 else "")
            add(cit, f"Q{m[1]}", question, h, "\n\n".join(g))
    for i, n in enumerate(notes, 1):
        add(f"{CITE} footnote {i}", f"footnote {i}", "Footnote", head, n)
    # A section split in parts shares its first citation; make ids unique and stable.
    seen = {}
    for c in chunks:
        seen[c.id] = seen.get(c.id, 0) + 1
        if seen[c.id] > 1:
            c.id = c.citation = f"{c.id} (part {seen[c.id]})"
    return chunks, warnings


def main() -> None:
    chunks, warnings = build()
    sizes = sorted(c.n_tokens for c in chunks)
    print(f"{len(chunks)} chunks from {NAME}; tokens min {sizes[0]}, median {sizes[len(sizes) // 2]}, max {sizes[-1]}")
    print("questions:", len({c.section for c in chunks if c.section.startswith("Q")}),
          "| footnotes:", sum(c.section.startswith("footnote") for c in chunks))
    for w in warnings:
        print("WARNING", w)


if __name__ == "__main__":
    main()
