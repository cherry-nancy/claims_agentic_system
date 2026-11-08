"""Invariants of the BPM Chapter 8 and FAQ chunks, and of the whole policy corpus (snf_pa.rag.corpus)."""
import re

import pytest
import yaml
from pypdf import PdfReader

from snf_pa.data.config import ROOT
from snf_pa.rag import bpm, corpus, faq
from snf_pa.rag.cfr import MAX_TOKENS
from snf_pa.rag.sources import DOCS, PDF

CARDS = ROOT / "policy_docs" / "derived" / "criterion_cards_GENERATED.yaml"


@pytest.fixture(scope="module")
def chunks():
    built, warnings = corpus.build()
    assert warnings == []
    return built


def norm(s: str) -> str:
    """Compare text, not layout: whitespace, dash and quote styles are ignored."""
    return re.sub(r"\s+", "", s.translate(str.maketrans("–—“”‘’", "--\"\"''")))


def test_every_registered_pdf_exists():
    assert all((DOCS / name).exists() for name in PDF)


def test_corpus_fits_the_budget_and_ids_are_unique(chunks):
    assert all(c.n_tokens <= MAX_TOKENS for c in chunks)
    assert len({c.id for c in chunks}) == len(chunks)
    assert {c.source_file.removeprefix("policy_docs/") for c in chunks} >= set(PDF)


def test_bpm_has_every_section_of_the_table_of_contents(chunks):
    pages = [p.extract_text() for p in PdfReader(DOCS / bpm.NAME).pages[:4]]
    toc = "\n".join(pages)
    toc = toc[:toc.index("(Rev.", toc.index("Transmittals Issued"))]
    listed = set(re.findall(r"(?m)^(\d{1,3}(?:\.\d+)*) ?[-–]", toc))
    covered = {p.removeprefix("BPM Ch.8 §") for c in chunks if c.source_file.endswith(bpm.NAME) for p in c.paragraphs}
    assert len(listed) == 66 and listed <= covered


def test_bpm_bodies_rebuild_the_chapter_exactly_once(chunks):
    """Checked against the raw PDF text with only the revision lines and the table of contents removed."""
    text = bpm.text_of(bpm.NAME)
    body = text[text.index("Transmittals Issued for this Chapter"):]
    first = next(m for m in bpm.HEADING.finditer(body) if m[1] == "10")
    body = body[first.start():]
    body = bpm.HEADING.sub(lambda m: f"{m[1]} - {m[2]}", body)  # heading without its "(Rev. ...)" line
    got = "".join(c.body for c in chunks if c.source_file.endswith(bpm.NAME))
    assert norm(got) == norm(body)


def test_bpm_examples_stay_with_their_text_and_long_sections_keep_their_context(chunks):
    mine = [c for c in chunks if c.source_file.endswith(bpm.NAME)]
    for c in mine:
        for m in re.finditer(r"EXAMPLE( \d+)?:?", c.body):
            assert len(re.findall(r"\w+", c.body[m.end():])) >= 10, c.id
    parts = [c for c in mine if "(part" in c.id and not c.id.endswith("(part 1)")]
    assert parts and all("(continued)" in c.header for c in parts)


def test_faq_items_are_whole_and_footnotes_are_cut_out(chunks):
    mine = [c for c in chunks if c.source_file.endswith(faq.NAME)]
    questions = [c for c in mine if c.section.startswith("Q")]
    assert {c.section for c in questions} == {f"Q{i}" for i in range(1, 15)}
    assert all(c.section_title.endswith("?") for c in questions)
    notes = [c for c in mine if c.section.startswith("footnote")]
    assert len(notes) == 5 and notes[1].body.startswith("15 U.S.C. 9401(3)")
    assert not any("15 U.S.C. 9401(3)" in c.body for c in questions)


def test_faq_bodies_rebuild_the_memo_and_nothing_is_lost(chunks):
    """Answer bodies rebuild the memo minus its footnotes; footnotes plus body account for every character of the
    PDF text except page numbers and the footnote numbers themselves."""
    from snf_pa.data.redact import is_deletion_of

    mine = [c for c in chunks if c.source_file.endswith(faq.NAME)]
    pages = [p.extract_text() for p in PdfReader(DOCS / faq.NAME).pages]
    body, notes = faq.split_footnotes(pages)
    assert norm("".join(c.body for c in mine if not c.section.startswith("footnote"))) == norm(body)
    assert [norm(c.body) for c in mine if c.section.startswith("footnote")] == [norm(n) for n in notes]
    raw = norm("".join(re.sub(r"(?m)^[ \t]*\d{1,3}[ \t]*$", "", p) for p in pages))
    assert is_deletion_of(norm(body), raw)
    assert len(raw) == len(norm(body)) + sum(len(norm(n)) + len(str(i)) for i, n in enumerate(notes, 1))


def test_card_quotes_from_the_pdfs_are_found_in_their_chunks(chunks):
    def quotes(x):
        if isinstance(x, str):
            yield x
        elif isinstance(x, list | dict):
            for v in (x.values() if isinstance(x, dict) else x):
                yield from quotes(v)

    checked = 0
    for card in yaml.safe_load(CARDS.read_text(encoding="utf-8"))["cards"]:
        if not card["source_file"].endswith(".pdf"):
            continue
        bodies = [norm(c.body) for c in chunks if c.source_file == card["source_file"]]
        for key, val in card.items():
            if key.endswith("_verbatim"):
                for q in quotes(val):
                    assert any(norm(q) in b for b in bodies), (card["id"], key, q[:60])
                    checked += 1
    assert checked >= 5


def test_every_expected_citation_of_the_retrieval_set_exists(chunks):
    from snf_pa.rag.index import EVAL, covers, groups

    items = yaml.safe_load(EVAL.read_text(encoding="utf-8"))["items"]
    dicts = [{"paragraphs": c.paragraphs} for c in chunks]
    assert 30 <= len(items) <= 300 and len({i["id"] for i in items}) == len(items)
    for it in items:
        for e in [e for g in groups(it) for e in g]:
            assert any(covers(c, e) for c in dicts), (it["id"], e)


def test_evidence_of_the_retrieval_set_is_in_an_expected_chunk(chunks):
    """Each evidence phrase is copied from a chunk the item expects (for expect_all, one phrase per group)."""
    from snf_pa.rag.index import EVAL, covers, groups

    def norm(s):
        return re.sub(r"\s+", " ", s).lower()

    items = [i for i in yaml.safe_load(EVAL.read_text(encoding="utf-8"))["items"] if "evidence" in i]
    assert len(items) >= 100
    for it in items:
        ev = it["evidence"] if isinstance(it["evidence"], list) else [it["evidence"]]
        assert len(ev) == len(groups(it)), it["id"]
        for phrase, g in zip(ev, groups(it), strict=True):
            assert any(norm(phrase) in norm(c.text) for c in chunks
                       if any(covers({"paragraphs": c.paragraphs}, e) for e in g)), (it["id"], phrase)


def test_a_chunk_covers_its_paragraphs_and_their_ancestors_only():
    from snf_pa.rag.index import covers

    c = {"paragraphs": ["42 CFR 409.34(a)(2)", "BPM Ch.8 §30.4.1", "CMS HPMS FAQ 2024-02-06 Q7 (part 2)"]}
    assert covers(c, "42 CFR 409.34") and covers(c, "42 CFR 409.34(a)") and covers(c, "BPM Ch.8 §30.4")
    assert covers(c, "CMS HPMS FAQ 2024-02-06 Q7")
    assert not covers(c, "42 CFR 409.3") and not covers(c, "BPM Ch.8 §30.4.2") and not covers(c, "CMS HPMS FAQ 2024-02-06 Q1")
    assert covers(c, "=BPM Ch.8 §30.4.1") and not covers(c, "=BPM Ch.8 §30.4")
