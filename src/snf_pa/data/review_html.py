"""Step 2: local HTML pages for the manual leakage review (dev cases only).

Each page shows the original note with what the strict packet removes: dropped sections grey,
sentences masked whole red, PT/OT sentences with a masked clause orange (hover shows the kept text).
Pages go to data/sample/review/ (gitignored); open index.html in a browser. Never prints note text.

Run:  $env:PYTHONPATH="src"; uv run python -m snf_pa.data.review_html [n_cases]
"""
import html
import sys

import polars as pl

from . import config as C
from .llm_guess import pick

CSS = """
body{font:14px/1.5 system-ui,sans-serif;margin:16px;max-width:1000px;color:#1b1b1b;background:#fff}
pre{white-space:pre-wrap;font:13px/1.45 ui-monospace,Consolas,monospace}
.drop{background:#e8e8e8;color:#777;text-decoration:line-through}
.mask{background:#ffd9d9;text-decoration:line-through}
.clause{background:#ffe7c2}
.legend span{padding:1px 6px;margin-right:8px}
table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:4px 8px;text-align:left}
"""


def render(text: str, marks: list[tuple[int, int, str, str]]) -> str:
    out, pos = [], 0
    for a, b, cls, title in sorted(marks):
        if a < pos:
            continue
        out.append(html.escape(text[pos:a]))
        t = f' title="{html.escape(title)}"' if title else ""
        out.append(f'<span class="{cls}"{t}>{html.escape(text[a:b])}</span>')
        pos = b
    out.append(html.escape(text[pos:]))
    return "".join(out)


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    d = C.SAMPLE_DIR
    out_dir = d / "review"
    out_dir.mkdir(exist_ok=True)
    cases = pl.read_csv(d / "sample_cases.csv")
    ids = pick(cases, n)
    notes = dict(pl.read_parquet(d / "notes_raw.parquet").select("hadm_id", "text").iter_rows())
    spans = pl.read_parquet(d / "spans_all.parquet").filter(pl.col("hadm_id").is_in(ids))
    strict = pl.read_parquet(d / "packets_strict.parquet").filter(pl.col("hadm_id").is_in(ids))
    log = pl.read_parquet(d / "redaction_log.parquet").filter(
        (pl.col("packet") == "strict") & pl.col("hadm_id").is_in(ids))
    kept_text = {(r["hadm_id"], r["span_id"]): r["text"] for r in strict.iter_rows(named=True)}
    info = {r["hadm_id"]: r for r in cases.iter_rows(named=True)}

    rows = []
    for k, h in enumerate(ids, 1):
        pos = {r["span_id"]: (r["start"], r["end"]) for r in spans.filter(pl.col("hadm_id") == h).iter_rows(named=True)}
        marks = []
        counts = {"drop": 0, "mask": 0, "clause": 0}
        for r in log.filter(pl.col("hadm_id") == h).iter_rows(named=True):
            a, b = pos[r["span_id"]]
            cls = "drop" if r["scope"] == "section" else ("clause" if r["scope"] == "clause" else "mask")
            counts[cls] += 1
            title = kept_text.get((h, r["span_id"]), "") if cls == "clause" else r["rule"]
            marks.append((a, b, cls, title))
        c = info[h]
        page = f"case_{k:02d}.html"
        body = (f"<!doctype html><meta charset=utf-8><title>Case {k}</title><style>{CSS}</style>"
                f"<p><a href=index.html>index</a> | case {k} | hadm_id {h} | {c['category']} | "
                f"<b>{c['discharge_location']}</b></p>"
                "<p class=legend><span class=drop>section dropped</span><span class=mask>sentence removed</span>"
                "<span class=clause>clause masked (hover)</span></p>"
                f"<pre>{render(notes[h], marks)}</pre>")
        (out_dir / page).write_text(body, encoding="utf-8")
        rows.append(f"<tr><td><a href={page}>{k}</a></td><td>{h}</td><td>{c['category']}</td>"
                    f"<td>{c['discharge_location']}</td><td>{counts['mask']}</td><td>{counts['clause']}</td>"
                    "<td></td></tr>")
    index = (f"<!doctype html><meta charset=utf-8><title>Leakage review</title><style>{CSS}</style>"
             "<h1>Step 2 leakage review (strict packet, dev cases)</h1>"
             "<p>For each case: is any disposition hint left in the unhighlighted text? Was clinical evidence "
             "removed by mistake? Note findings in the last column of your own copy.</p>"
             "<table><tr><th>#</th><th>hadm_id</th><th>category</th><th>discharge</th>"
             "<th>sentences removed</th><th>clauses masked</th><th>notes</th></tr>" + "".join(rows) + "</table>")
    (out_dir / "index.html").write_text(index, encoding="utf-8")
    print(f"wrote {len(ids)} pages to {out_dir}")


if __name__ == "__main__":
    main()
