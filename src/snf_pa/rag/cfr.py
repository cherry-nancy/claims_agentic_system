"""Structure-aware chunks of the eCFR XML in policy_docs/ for the policy RAG index (plan Step 3).

Run from the project root:
    PYTHONPATH=src uv run python -m snf_pa.rag.cfr

Each section is parsed into its paragraph tree: (a) > (1) > (i) > (A) > italic (1) > italic (i). A paragraph
whose text (with its sub-paragraphs) fits in the budget stays whole; a larger one is split between its
sub-paragraphs, never inside one. Neighbouring paragraphs are packed together up to the budget.

Each chunk has:
  body    - the source text it covers. A section's bodies, in order, join back to the whole section exactly once.
  header  - the section heading plus the lead-in of each enclosing paragraph not already in the body, so a chunk
            split from a long paragraph still says what it is part of.
  text    - header + body; this is what gets indexed.
The chunk id is its citation, e.g. "42 CFR 409.33(c)(1)-(c)(4)".

Writes derived/rag/cfr_chunks.jsonl (gitignored; rebuilt from policy_docs/).
"""
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field

from snf_pa.data.config import ROOT
from snf_pa.rag.sources import CFR, DOCS

OUT = ROOT / "derived" / "rag" / "cfr_chunks.jsonl"
MAX_TOKENS = 800  # whole chunk, header included (plan Step 3: 300-800 tokens)
MAX_LEADIN_CHARS = 300  # a lead-in repeated in a header is cut to this length

# Paragraph levels. Italic markers are levels 5 and 6.
FIRST = {1: "a", 2: "1", 3: "i", 4: "A", 5: "1", 6: "i"}
ITAL_ON, ITAL_OFF = "\x01", "\x02"
MARK = re.compile(rf"\(({ITAL_ON}?)([A-Za-z0-9]+){ITAL_OFF}?\)\s*")
# A second paragraph starts right after the first one's heading: "(a) <I>Heading</I>—(1) ...",
# "(i) <I>Heading.</I> (A) ..." or a plain heading "(c) Medical necessity ... provisions—(1) ...".
INLINE = re.compile(rf"(?:{ITAL_ON}[^{ITAL_OFF}]*{ITAL_OFF}\s*—?|[^—().{ITAL_ON}]{{1,150}}—)\s*"
                    rf"(?=\({ITAL_ON}?[A-Za-z0-9]+{ITAL_OFF}?\))")


def tokens(s: str) -> int:
    """Rough token count (about 4 characters per token for English legal text)."""
    return -(-len(s) // 4)


ROMAN = [(10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")]


def to_roman(n: int) -> str:
    out = ""
    for v, r in ROMAN:
        while n >= v:
            out, n = out + r, n - v
    return out


ROMANS = {to_roman(n): n for n in range(1, 40)}


def succ(level: int, m: str) -> str:
    if level in (2, 5):
        return str(int(m) + 1)
    if level in (3, 6):
        return to_roman(ROMANS[m] + 1) if m in ROMANS else ""

    return chr(ord(m) + 1)


def candidates(m: str, italic: bool) -> list[int]:
    if italic:
        return [5] if m.isdigit() else [6]
    if m.isdigit():
        return [2]
    if m.isupper():
        return [4]
    return ([1] if len(m) == 1 else []) + ([3] if m in ROMANS else [])


@dataclass
class Para:
    label: tuple[str, ...]  # () is the section itself (introductory text)
    text: list[str] = field(default_factory=list)
    children: list["Para"] = field(default_factory=list)

    def full(self) -> str:
        return "\n".join(t for t in self.text + [c.full() for c in self.children] if t)

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()

    def labels(self) -> list[tuple[str, ...]]:
        return [p.label for p in self.walk()]


@dataclass
class Chunk:
    id: str
    citation: str
    section: str
    section_title: str
    paragraphs: list[str]
    header: str
    body: str
    text: str
    n_tokens: int
    source_file: str
    version: str
    program: str
    tier: int
    history: str


def marked_text(p: ET.Element) -> str:
    """Text of a <P> with italics wrapped in sentinels and footnote references dropped."""
    out = [p.text or ""]
    for e in p:
        if e.tag == "I":
            out.append(ITAL_ON + "".join(e.itertext()) + ITAL_OFF)
        elif e.tag not in ("SU", "FTREF"):
            out.append("".join(e.itertext()))
        out.append(e.tail or "")
    return re.sub(r"\s+", " ", "".join(out)).strip()


def pieces(s: str) -> list[tuple[str | None, bool, str]]:
    """One <P> -> [(marker, italic, text)]. "(3)(i) X" gives ("3", "") then ("i", "X")."""
    out = []
    while True:
        m = MARK.match(s)
        if not m:
            break
        rest = s[m.end():]
        if MARK.match(rest):  # stacked markers: this paragraph has no text of its own
            out.append((m.group(2), bool(m.group(1)), s[:m.end()].strip()))
            s = rest
            continue
        inline = INLINE.match(rest)
        if inline:
            out.append((m.group(2), bool(m.group(1)), s[:m.end() + inline.end()].strip()))
            s = rest[inline.end():]
            continue
        out.append((m.group(2), bool(m.group(1)), s))
        return out
    return out + [(None, False, s)] if s else out


def clean(s: str) -> str:
    return s.replace(ITAL_ON, "").replace(ITAL_OFF, "")


def parse_section(sec: ET.Element) -> tuple[Para, list[str], list[str]]:
    """Section -> (paragraph tree, footnotes, warnings for markers that break the expected sequence)."""
    items = [it for p in sec.findall("P") for it in pieces(marked_text(p))]
    root, warnings = Para(()), []
    stack: list[tuple[int, Para]] = []  # (level, paragraph), outermost first
    for k, (m, italic, text) in enumerate(items):
        if m is None:  # unmarked text continues the last paragraph (or is the section's intro)
            (stack[-1][1] if stack else root).text.append(clean(text))
            continue
        cur = {lv: p.label[-1] for lv, p in stack}
        deepest = stack[-1][0] if stack else 0
        fit = [lv for lv in candidates(m, italic)
               if (succ(lv, cur[lv]) == m if lv in cur else (m == FIRST[lv] and lv == deepest + 1))]
        if not fit:  # a list under an undesignated paragraph skips a level, e.g. 412.622(c) definitions -> (i)
            fit = [lv for lv in candidates(m, italic) if lv > deepest + 1 and m == FIRST[lv]]
        if len(fit) > 1:  # e.g. "(i)" after "(h)(2)": letter or roman? Whichever sequence continues first wins.
            later = [x[0] for x in items[k + 1:] if x[0]]
            nxt = {lv: succ(lv, m) for lv in fit}
            fit = sorted(fit, key=lambda lv: later.index(nxt[lv]) if nxt[lv] in later else len(later))
        if not fit:
            warnings.append(f"{sec.get('N')}: unexpected ({m}) after {[p.label for _, p in stack][-1:]}")
            fit = [max((lv for lv in candidates(m, italic) if lv <= deepest + 1), default=candidates(m, italic)[0])]
        level = fit[0]
        while stack and stack[-1][0] >= level:
            stack.pop()
        node = Para((stack[-1][1].label if stack else ()) + (m,), [clean(text)])
        (stack[-1][1] if stack else root).children.append(node)
        stack.append((level, node))
    notes = [re.sub(r"\s+", " ", "".join(p.itertext())).strip() for f in sec.findall("FTNT") for p in f.findall("P")]
    return root, notes, warnings


def cite(sec: str, label: tuple[str, ...]) -> str:
    return f"42 CFR {sec}" + ("".join(f"({x})" for x in label) if label else " (introductory text)")


def chunk_para(node: Para, leadins: list[str], head: str) -> list[tuple[str, list]]:
    """Paragraph -> [(header, [paragraph labels])], splitting only between sub-paragraphs."""
    header = "\n".join([head] + leadins)
    if tokens(header + "\n\n" + node.full()) <= MAX_TOKENS or not node.children:
        return [(header, node.labels())]
    own = " ".join(node.text)
    inner = leadins + ([own[:MAX_LEADIN_CHARS] + ("…" if len(own) > MAX_LEADIN_CHARS else "")] if own else [])
    inner_header = "\n".join([head] + inner)
    out, group, size = [], ([node.label] if own else []), tokens(header + "\n\n" + own)
    group_header = header
    for c in node.children:
        n = tokens(c.full()) + 1
        if size + n > MAX_TOKENS and group:
            out.append((group_header, group))
            group, group_header, size = [], inner_header, tokens(inner_header) + 1
        if tokens(inner_header + "\n\n" + c.full()) > MAX_TOKENS:
            if group:
                out.append((group_header, group))
            out += chunk_para(c, inner, head)
            group, group_header, size = [], inner_header, tokens(inner_header) + 1
        else:
            group += c.labels()
            size += n
    if group:
        out.append((group_header, group))
    return out


def chunk_file(name: str) -> tuple[list[Chunk], list[str]]:
    meta = CFR[name]
    root_el = ET.parse(DOCS / name).getroot()
    chunks, warnings = [], []
    for sec in root_el.iter("DIV8"):
        num = sec.get("N")
        title = re.sub(r"^§\s*\S+\s*", "", "".join(sec.find("HEAD").itertext())).strip()
        head = f"42 CFR {num} {title}"
        cita = sec.find("CITA")
        history = re.sub(r"\s+", " ", "".join(cita.itertext())).strip() if cita is not None else ""
        tree, notes, warn = parse_section(sec)
        warnings += warn
        texts = {p.label: "\n".join(t for t in p.text if t) for p in tree.walk()}
        groups = chunk_para(tree, [], head)
        groups += [(head, [("fn", str(i + 1))]) for i in range(len(notes))]
        texts.update({("fn", str(i + 1)): n for i, n in enumerate(notes)})
        for header, labels in groups:
            body = "\n".join(texts[lab] for lab in labels if texts[lab])
            header = "\n".join(line for line in header.split("\n") if line not in body)
            if labels[0][:1] == ("fn",):
                paras = [f"42 CFR {num} footnote {labels[0][1]}"]
                citation = paras[0]
            else:
                paras = [cite(num, lab) for lab in labels]
                tops = [lab for lab in labels if len(lab) <= 1 or lab[:-1] not in labels]
                citation = (f"42 CFR {num}" if labels == tree.labels() else paras[0] if len(tops) == 1
                            else f"{cite(num, tops[0])}–{''.join(f'({x})' for x in tops[-1])}")
            text = header + "\n\n" + body
            chunks.append(Chunk(citation, citation, num, title, paras, header, body, text, tokens(text),
                                f"policy_docs/{name}", meta["version"], meta["program"], meta["tier"], history))
    return chunks, warnings


def build() -> tuple[list[Chunk], list[str]]:
    chunks, warnings = [], []
    for name in CFR:
        c, w = chunk_file(name)
        chunks += c
        warnings += w
    return chunks, warnings


def main() -> None:
    chunks, warnings = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(asdict(c), ensure_ascii=False) + "\n")
    sizes = sorted(c.n_tokens for c in chunks)
    print(f"{len(chunks)} chunks from {len(CFR)} files -> {OUT.relative_to(ROOT)}")
    print(f"tokens: min {sizes[0]}, median {sizes[len(sizes) // 2]}, max {sizes[-1]}")
    for w in warnings:
        print("WARNING", w)


if __name__ == "__main__":
    main()
