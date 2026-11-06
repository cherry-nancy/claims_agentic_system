"""Invariants of the CFR chunks (snf_pa.rag.cfr): complete, within budget, citable, and consistent with the cards."""
import re
import xml.etree.ElementTree as ET

import pytest
import yaml

from snf_pa.data.config import ROOT
from snf_pa.rag import cfr
from snf_pa.rag.sources import CFR, DOCS

CARDS = ROOT / "policy_docs" / "derived" / "criterion_cards_GENERATED.yaml"


@pytest.fixture(scope="module")
def built():
    return cfr.build()


def norm(s: str) -> str:
    """Compare text, not layout: whitespace (split paragraphs are rejoined with a newline) and quote style
    (the cards use straight quotes where the eCFR has curly ones) are ignored."""
    return re.sub(r"\s+", "", s.translate(str.maketrans("“”‘’", "\"\"''")))


def test_every_registered_file_exists_and_every_xml_is_registered():
    assert {p.name for p in DOCS.glob("*.xml")} == set(CFR)


def test_parser_has_no_unexpected_markers(built):
    assert built[1] == []


def test_chunks_fit_the_budget_and_ids_are_unique(built):
    chunks = built[0]
    assert all(c.n_tokens <= cfr.MAX_TOKENS for c in chunks)
    assert len({c.id for c in chunks}) == len(chunks)


def test_bodies_rebuild_each_section_exactly_once(built):
    """Checked against a plain extraction of the <P> text, independent of the paragraph parser."""
    by_section = {}
    for c in built[0]:
        if "footnote" not in c.citation:
            by_section.setdefault(c.section, []).append(c.body)
    for name in CFR:
        for sec in ET.parse(DOCS / name).getroot().iter("DIV8"):
            plain = " ".join(cfr.clean(cfr.marked_text(p)) for p in sec.findall("P"))
            assert norm(" ".join(by_section[sec.get("N")])) == norm(plain), sec.get("N")


def test_paragraph_labels_are_citable(built):
    paras = {p for c in built[0] for p in c.paragraphs}
    for p in ["42 CFR 409.30(a)(1)", "42 CFR 409.30(b)(2)(ii)", "42 CFR 409.33(c)(5)", "42 CFR 409.34(a)(2)",
              "42 CFR 412.622(a)(3)(ii)", "42 CFR 422.101(c)(1)(i)(A)", "42 CFR 422.101(c)(2)",
              "42 CFR 422.112(b)(8)(i)(A)", "42 CFR 422.568(b)(2)(ii)(A)(1)", "42 CFR 424.20(e)(2)(i)(B)"]:
        assert p in paras, p


def test_card_quotes_are_found_in_a_chunk_of_the_cited_section(built):
    def quotes(x):
        if isinstance(x, str):
            yield x
        elif isinstance(x, list):
            for v in x:
                yield from quotes(v)
        elif isinstance(x, dict):
            for v in x.values():
                yield from quotes(v)

    cards = yaml.safe_load(CARDS.read_text(encoding="utf-8"))["cards"]
    checked = 0
    for card in cards:
        name = card["source_file"].removeprefix("policy_docs/")
        if name not in CFR:
            continue  # FAQ-based guardrails are checked when the PDFs are chunked
        bodies = [norm(c.body) for c in built[0]
                  if c.source_file == card["source_file"] and c.section in card["cfr"]]
        for key, val in card.items():
            if key.endswith("_verbatim"):
                for q in quotes(val):
                    assert any(norm(q) in b for b in bodies), (card["id"], key, q[:60])
                    checked += 1
    assert checked > 50
