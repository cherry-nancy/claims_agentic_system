"""Structure-aware chunks of the Medicare Benefit Policy Manual, Chapter 8 (SNF) for the policy RAG index.

Run from the project root:
    PYTHONPATH=src uv run python -m snf_pa.rag.bpm

The chapter is a tree of numbered sections (30 > 30.2 > 30.2.3 > 30.2.3.1), each opened by its heading and its own
revision line, e.g. "30.2.3 - ... (Rev. 179, Issued: 01-14-14, ...)". A section whose subtree fits the budget stays
whole; a larger one gives its own text as one or more chunks and its subsections are chunked the same way, with
neighbouring small subsections packed together. Text inside a section is split only between paragraphs, and an
"EXAMPLE" label stays with the paragraph it introduces.

Each chunk has, like snf_pa.rag.cfr:
  body    - the source text it covers; a section's bodies, in order, join back to its text exactly once.
  header  - chapter and section path; for a continued section also "(continued)" and the last lead-in paragraph
            before the chunk (one ending in ":", e.g. the sentence introducing a list of skilled services).
  text    - header + body; this is what gets indexed.
The chunk id is its citation, e.g. "BPM Ch.8 §30.2.3.1" or "BPM Ch.8 §30.4 (part 2)".
"""
import re
from dataclasses import dataclass, field

from pypdf import PdfReader

from snf_pa.rag.cfr import MAX_LEADIN_CHARS, MAX_TOKENS, Chunk, tokens
from snf_pa.rag.sources import DOCS, PDF

NAME = "bp102c08.pdf"
CHAPTER = "BPM Ch.8"
TITLE = "Coverage of Extended Care (SNF) Services Under Hospital Insurance"
# "30.2.3 - Title" (the title may wrap onto up to three lines), then "(Rev. ...)" on the next line.
HEADING = re.compile(r"(?m)^(\d{1,3}(?:\.\d+)*) ?[-–] ?([^\n]+(?:\n(?![ \t]*\(Rev)[ \t]*\S[^\n]*){0,2})\s*\n[ \t]*\((Rev\.[^)]*)\)")


@dataclass
class Section:
    number: str
    title: str
    rev: str
    paras: list[str]
    children: list["Section"] = field(default_factory=list)

    @property
    def key(self) -> tuple[int, ...]:
        return tuple(int(x) for x in self.number.split("."))

    @property
    def heading(self) -> str:
        return f"{self.number} - {self.title}"

    def own(self) -> list[str]:
        return [self.heading] + self.paras

    def full(self) -> str:
        return "\n\n".join(self.own() + [c.full() for c in self.children])

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()


def text_of(name: str) -> str:
    return "\n".join(p.extract_text() for p in PdfReader(DOCS / name).pages)


def paragraphs(s: str) -> list[str]:
    """Hard-wrapped PDF text -> paragraphs (blank-line separated), each on one line. An EXAMPLE label that stands
    alone is joined to the paragraph after it."""
    paras = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n[ \t]*\n", s)]
    paras = [p for p in paras if p]
    out = []
    for p in paras:
        if out and re.fullmatch(r"EXAMPLE( \d+)?:?", out[-1]):
            out[-1] += " " + p
        else:
            out.append(p)
    return out


def parse(text: str) -> tuple[list[Section], list[str]]:
    """Body of the chapter (after the table of contents) -> section tree, warnings."""
    found, warnings = [], []
    for m in HEADING.finditer(text):
        key = tuple(int(x) for x in m[1].split("."))
        if found and key <= found[-1][0]:
            continue  # a cross-reference or the table of contents, not a heading
        found.append((key, m))
    roots, stack = [], []
    for k, (key, m) in enumerate(found):
        end = found[k + 1][1].start() if k + 1 < len(found) else len(text)
        sec = Section(m[1], re.sub(r"\s+", " ", m[2]).strip(), re.sub(r"\s+", " ", m[3]).strip(),
                      paragraphs(text[m.end():end]))
        while stack and not (key[:len(stack[-1].key)] == stack[-1].key and len(key) > len(stack[-1].key)):
            stack.pop()
        if stack and len(key) != len(stack[-1].key) + 1:
            warnings.append(f"§{m[1]} skips a level under §{stack[-1].number}")
        (stack[-1].children if stack else roots).append(sec)
        stack.append(sec)
    return roots, warnings


def fit(para: str, header: str) -> list[str]:
    """A paragraph too large for one chunk -> runs of whole sentences that fit (rare: one unbroken list)."""
    if tokens(header + "\n\n" + para) <= MAX_TOKENS:
        return [para]
    out, cur = [], ""
    for sent in re.split(r"(?<=[.;:])\s+(?=[A-Z0-9•(])", para):
        if cur and tokens(header + "\n\n" + cur + " " + sent) > MAX_TOKENS - 80:  # room for a continuation header
            out.append(cur)
            cur = ""
        cur = f"{cur} {sent}".strip()
    return out + [cur] if cur else out


def split_paras(paras: list[str], header: str, cont: str) -> list[tuple[str, list[str]]]:
    """Paragraphs -> [(header, paragraphs)] within the budget, splitting only between paragraphs. Chunks after the
    first get `cont` plus the last lead-in paragraph before them as header."""
    out, group, leadin = [], [], ""
    for p in [x for para in paras for x in fit(para, header)]:
        if group and tokens(header + "\n\n" + "\n\n".join(group + [p])) > MAX_TOKENS:
            out.append((header, group))
            cut = leadin[:MAX_LEADIN_CHARS] + ("…" if len(leadin) > MAX_LEADIN_CHARS else "")
            header, group = cont + (f"\n{cut}" if leadin else ""), []
        group.append(p)
        if p.endswith(":"):
            leadin = p
    if group:
        out.append((header, group))
    return out


def chunk_section(sec: Section, parents: list[Section]) -> list[tuple[str, list[str], list[str]]]:
    """-> [(header, section numbers covered, body paragraphs)]. The header holds the chapter and the ancestors'
    headings; the section's own heading is the first line of its body."""
    path = "\n".join([f"{CHAPTER} {TITLE}"] + [f"§{s.number} {s.title}" for s in parents])
    if tokens(path + "\n\n" + sec.full()) <= MAX_TOKENS:
        return [(path, [s.number for s in sec.walk()], [sec.full()])]
    inner = path + f"\n§{sec.number} {sec.title}"
    out = [(h, [sec.number], g) for h, g in split_paras(sec.own(), path, inner + " (continued)")]
    group, nums, size = [], [], tokens(inner)
    for c in sec.children:
        sub = chunk_section(c, parents + [sec])
        if len(sub) == 1:  # a whole subsection: pack it with its small neighbours
            _, n, b = sub[0]
            n_tok = tokens("\n\n".join(b)) + 1
            if group and size + n_tok > MAX_TOKENS:
                out.append((inner, nums, group))
                group, nums, size = [], [], tokens(inner)
            group, nums, size = group + b, nums + n, size + n_tok
        else:
            if group:
                out.append((inner, nums, group))
                group, nums, size = [], [], tokens(inner)
            out += sub
    if group:
        out.append((inner, nums, group))
    return out


def citation(nums: list[str]) -> str:
    return f"{CHAPTER} §{nums[0]}" if len(nums) == 1 else f"{CHAPTER} §{nums[0]}–§{nums[-1]}"


def build() -> tuple[list[Chunk], list[str]]:
    text = text_of(NAME)
    body = text[text.index("Transmittals Issued for this Chapter"):]
    roots, warnings = parse(body)
    meta, chunks = PDF[NAME], []
    by_num = {s.number: s for r in roots for s in r.walk()}
    for r in roots:
        for header, nums, paras in chunk_section(r, []):
            cit = citation(nums)
            same = [c for c in chunks if c.citation.split(" (part")[0] == cit]
            if same:
                if len(same) == 1:
                    same[0].citation = same[0].id = cit + " (part 1)"
                cit += f" (part {len(same) + 1})"
            b = "\n\n".join(paras)
            revs = sorted({by_num[n].rev for n in nums})
            chunks.append(Chunk(cit, cit, nums[0], by_num[nums[0]].title, [f"{CHAPTER} §{n}" for n in nums],
                                header, b, header + "\n\n" + b, tokens(header + "\n\n" + b), f"policy_docs/{NAME}",
                                meta["version"], meta["program"], meta["tier"], "; ".join(revs)))
    return chunks, warnings


def main() -> None:
    chunks, warnings = build()
    sizes = sorted(c.n_tokens for c in chunks)
    print(f"{len(chunks)} chunks from {NAME}; tokens min {sizes[0]}, median {sizes[len(sizes) // 2]}, max {sizes[-1]}")
    for w in warnings:
        print("WARNING", w)


if __name__ == "__main__":
    main()
