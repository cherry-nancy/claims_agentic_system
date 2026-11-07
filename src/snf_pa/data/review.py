"""Blind review page for the redacted notes (dev split only): guess first, then see what was removed.

Run from the project root (after snf_pa.data.redact; leakage_llm is optional):
    PYTHONPATH=src uv run python -m snf_pa.data.review [--mode strict] [--n 50]

For each case the page shows the redacted note exactly as the model sees it. The reviewer guesses the destination
and notes what gave it away, then reveals: the original note with every removal marked (red = removed by a rule,
grey = section dropped), the true destination, and the local LLM's guess and quotes if leakage_llm has been run
(leak-candidate quotes are flagged). The reviewer then records whether anything left in the note leaks.
Cases come in seeded random order, so the destination cannot be read from their position, except that cases with a
leak candidate (up to MAX_FLAGGED) are put last, so a short review still reads them.

Leak candidates are recomputed here against the current notes and rules: a quote is one if it is still in the note
the page shows and matches a disposition rule. A quote of text a later rule removed is no longer flagged.

Writes data/sample/review/blind_review_{mode}.html (gitignored). The page holds note text: open it locally only,
never upload or publish it. Answers stay in the browser (localStorage) until "Download answers" saves them as JSON.
"""
import argparse
import html
import json

import polars as pl

from snf_pa.data import config as C
from snf_pa.data.leakage_llm import DEST, squash
from snf_pa.data.redact import FILES, MODES, TRIGGERS, VERSION

OUT_DIR = C.SAMPLE_DIR / "review"
MAX_FLAGGED = 10


def marked(original: str, spans: list[dict]) -> str:
    """The original note as HTML with removals marked. Later span kinds override earlier ones."""
    state = [""] * len(original)  # "" = untouched (headings, line breaks), "drop", "cut"
    for sp in sorted(spans, key=lambda s: s["status"] != "section_dropped"):
        a, b = sp["start"], sp["end"]
        if sp["status"] == "section_dropped":
            state[a:b] = ["drop"] * (b - a)
        elif sp["status"] == "removed":
            state[a:b] = ["cut"] * (b - a)
        else:  # kept or trimmed: align the shown text to the source, the rest of the source was cut
            it = iter(sp["text"])
            keep = next(it, None)
            for i in range(a, b):
                if keep is not None and original[i] == keep:
                    state[i], keep = "", next(it, None)
                else:
                    state[i] = "" if original[i].isspace() else "cut"
    out, i = [], 0
    while i < len(original):
        j = i
        while j < len(original) and state[j] == state[i]:
            j += 1
        text = html.escape(original[i:j])
        out.append(f'<span class="{state[i]}">{text}</span>' if state[i] else text)
        i = j
    return "".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=list(MODES), default="strict")
    ap.add_argument("--n", type=int, default=50, help="cases (0 = all dev cases)")
    args = ap.parse_args()

    cases = pl.concat([pl.read_csv(C.SAMPLE_DIR / f"{f}.csv", infer_schema_length=0)
                       .select("hadm_id", "discharge_location", "split") for f in ["sample_cases1", "sample_cases1_supp"]])
    raw = pl.concat([pl.read_parquet(C.SAMPLE_DIR / f"{f}.parquet").select("note_id", "hadm_id", "text") for f in FILES])
    red = pl.concat([pl.read_parquet(C.SAMPLE_DIR / f"{f}.parquet") for f in FILES.values()])
    assert (red["redaction_version"] == VERSION).all(), "rerun snf_pa.data.redact first"
    spans = pl.concat([pl.read_parquet(C.SAMPLE_DIR / f"{f}_spans.parquet") for f in FILES.values()])
    spans = spans.filter(pl.col("mode") == args.mode)
    d = (red.filter(pl.col("mode") == args.mode).select("note_id", "hadm_id", pl.col("text").alias("packet"))
         .join(raw.select("note_id", "text"), on="note_id").with_columns(pl.col("hadm_id").cast(pl.String))
         .join(cases, on="hadm_id").filter(pl.col("split") == "dev")
         .with_columns(k=pl.col("hadm_id").hash(C.SEED)).sort("k"))
    llm_file = C.SAMPLE_DIR / f"leakage_llm_{args.mode}.parquet"
    llm = None
    if llm_file.exists():
        packets = {r["hadm_id"]: squash(r["packet"]) for r in d.iter_rows(named=True)}
        llm = pl.read_parquet(llm_file).filter(pl.col("hadm_id").is_in(list(packets))).with_columns(
            verbatim=pl.struct("hadm_id", "quote").map_elements(
                lambda x: bool(x["quote"]) and squash(x["quote"]) in packets[x["hadm_id"]], return_dtype=pl.Boolean),
            rule=pl.col("quote").map_elements(lambda q: [k for k, rx in TRIGGERS.items() if rx.search(q)],
                                              return_dtype=pl.List(pl.String)))
        llm = llm.with_columns(leak_candidate=pl.col("verbatim") & (pl.col("rule").list.len() > 0))
        flagged = set(llm.filter("leak_candidate")["hadm_id"].unique().sort().head(MAX_FLAGGED))
        d = pl.concat([d.filter(~pl.col("hadm_id").is_in(list(flagged))), d.filter(pl.col("hadm_id").is_in(list(flagged)))])
    if args.n:
        n_flag = len(flagged) if llm is not None else 0
        d = pl.concat([d.head(d.height - n_flag).head(args.n - n_flag), d.tail(n_flag)]) if n_flag else d.head(args.n)

    by_note = {k[0]: g.to_dicts() for k, g in spans.group_by("note_id")}
    data = []
    for k, r in enumerate(d.iter_rows(named=True), 1):
        item = {"case": k, "hadm_id": r["hadm_id"], "packet": r["packet"], "truth": DEST[r["discharge_location"]],
                "original": marked(r["text"], by_note[r["note_id"]]), "llm": None}
        if llm is not None and (q := llm.filter(pl.col("hadm_id") == r["hadm_id"])).height:
            item["llm"] = {"guess": q["guess"][0], "confidence": q["confidence"][0],
                           "quotes": q.filter(pl.col("quote") != "").select("quote", "kind", "verbatim",
                                                                             "leak_candidate").to_dicts()}
        data.append(item)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"blind_review_{args.mode}.html"
    page = PAGE.replace("__DATA__", json.dumps(data).replace("</", "<\\/")).replace("__MODE__", args.mode)
    out.write_text(page.replace("__VERSION__", VERSION), encoding="utf-8")
    n_flag = sum(any(q["leak_candidate"] for q in x["llm"]["quotes"]) for x in data if x["llm"])
    print(f"{len(data)} dev cases ({args.mode}, {VERSION}); LLM results {'included' if llm is not None else 'absent'}; "
          f"{n_flag} with a leak candidate (last on the page)")
    print(f"-> {out.relative_to(C.ROOT)}  (local only: contains note text)")


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Blind Redaction Review</title>
<style>
:root { --bg:#fbfbf9; --fg:#1d1d1b; --muted:#6b6b66; --line:#deded8; --card:#fff; --accent:#2f5d8a;
        --cut:#fbe1de; --cut-fg:#9b2c1f; --drop:#ececea; --warn:#fff3cd; }
@media (prefers-color-scheme: dark) { :root { --bg:#191918; --fg:#e8e8e3; --muted:#9a9a93; --line:#33332f;
        --card:#222220; --accent:#8ab4e0; --cut:#4a2420; --cut-fg:#f2b8ae; --drop:#2c2c29; --warn:#4a3f1c; } }
* { box-sizing:border-box } body { margin:0; background:var(--bg); color:var(--fg);
  font:15px/1.5 -apple-system, system-ui, sans-serif }
header { position:sticky; top:0; background:var(--bg); border-bottom:1px solid var(--line); padding:10px 16px;
  display:flex; gap:12px; align-items:center; flex-wrap:wrap; z-index:1 }
header b { margin-right:auto } button, select { font:inherit; padding:5px 12px; border-radius:6px;
  border:1px solid var(--line); background:var(--card); color:var(--fg); cursor:pointer }
button.primary { background:var(--accent); color:var(--bg); border-color:var(--accent) }
main { max-width:1100px; margin:0 auto; padding:16px }
.note { white-space:pre-wrap; font:13px/1.45 ui-monospace, Menlo, monospace; background:var(--card);
  border:1px solid var(--line); border-radius:8px; padding:14px; max-height:60vh; overflow:auto }
.cut { background:var(--cut); color:var(--cut-fg); text-decoration:line-through }
.drop { background:var(--drop); color:var(--muted) }
form, .reveal { background:var(--card); border:1px solid var(--line); border-radius:8px; padding:14px; margin-top:14px }
label { margin-right:14px; white-space:nowrap } textarea { width:100%; font:inherit; min-height:52px;
  background:var(--bg); color:var(--fg); border:1px solid var(--line); border-radius:6px; padding:6px }
.muted { color:var(--muted) } .flag { background:var(--warn); padding:0 4px; border-radius:3px }
li { margin:4px 0 }
</style></head><body>
<header><b>Blind review · __MODE__ · __VERSION__</b><span id="pos" class="muted"></span>
<button id="prev">←</button><button id="next">→</button><button id="dl">Download answers</button></header>
<main>
<p class="muted">Read the note as the model sees it. Guess first; reveal only after saving the guess.</p>
<div id="packet" class="note"></div>
<form id="guess">
  <div><b>Destination?</b>
    <label><input type="radio" name="g" value="SNF"> SNF</label>
    <label><input type="radio" name="g" value="IRF"> IRF</label>
    <label><input type="radio" name="g" value="home_health"> Home health</label>
    <label><input type="radio" name="g" value="home"> Home</label>
    <label><input type="radio" name="g" value="unsure"> Can't tell</label></div>
  <p><b>What gave it away?</b> (quote or describe; leave empty if nothing)</p><textarea name="why"></textarea>
  <p><button class="primary" type="submit">Save guess and reveal</button></p>
</form>
<div id="reveal" class="reveal" hidden>
  <p><b>Truth:</b> <span id="truth"></span> · <b>Your guess:</b> <span id="mine"></span></p>
  <div id="llm"></div>
  <p class="muted">Original note: <span class="cut">removed by a rule</span> · <span class="drop">section dropped</span></p>
  <div id="orig" class="note"></div>
  <form id="verdict">
    <p><b>Does anything left in the redacted note reveal the destination (not clinical status)?</b>
      <label><input type="radio" name="leak" value="no"> No</label>
      <label><input type="radio" name="leak" value="yes"> Yes</label></p>
    <p><b>Over-redaction?</b> (clinical fact removed)
      <label><input type="radio" name="over" value="no"> No</label>
      <label><input type="radio" name="over" value="yes"> Yes</label></p>
    <textarea name="notes" placeholder="Which phrase, and should a rule change?"></textarea>
    <p><button class="primary" type="submit">Save and next</button></p>
  </form>
</div>
</main>
<script>
const DATA = __DATA__, KEY = "blind_review___MODE_____VERSION__";
let ans = {}; try { ans = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(ans)); } catch (e) {} };
let i = DATA.findIndex(d => !(ans[d.case] && ans[d.case].leak)); if (i < 0) i = 0;
const $ = id => document.getElementById(id);
const esc = s => s.replace(/[&<>]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
function show() {
  const d = DATA[i], a = ans[d.case] || {};
  $("pos").textContent = `case ${i + 1} / ${DATA.length} · ${Object.values(ans).filter(x => x.leak).length} done`;
  $("packet").textContent = d.packet;
  const g = $("guess"); g.reset(); g.querySelectorAll("input,textarea,button").forEach(e => e.disabled = !!a.guess);
  if (a.guess) { g.querySelector(`[value="${a.guess}"]`).checked = true; g.why.value = a.why || ""; }
  $("reveal").hidden = !a.guess;
  if (a.guess) reveal(d, a);
  window.scrollTo(0, 0);
}
function reveal(d, a) {
  $("truth").textContent = d.truth; $("mine").textContent = a.guess;
  $("orig").innerHTML = d.original;
  $("llm").innerHTML = d.llm ? `<p><b>LLM guess:</b> ${d.llm.guess} (${d.llm.confidence})</p><ul>` +
    d.llm.quotes.map(q => `<li>${q.leak_candidate ? '<span class="flag">leak candidate</span> ' : ""}` +
      `<i>${q.kind}</i>${q.verbatim ? "" : " (not in note)"}: ${esc(q.quote)}</li>`).join("") + "</ul>"
    : '<p class="muted">No LLM result for this case.</p>';
  const v = $("verdict"); v.reset();
  if (a.leak) v.querySelector(`[name=leak][value="${a.leak}"]`).checked = true;
  if (a.over) v.querySelector(`[name=over][value="${a.over}"]`).checked = true;
  v.notes.value = a.notes || "";
}
$("guess").onsubmit = e => { e.preventDefault(); const f = e.target;
  if (!f.g.value) return alert("Pick a destination (or Can't tell) first.");
  ans[DATA[i].case] = { hadm_id: DATA[i].hadm_id, truth: DATA[i].truth, guess: f.g.value, why: f.why.value };
  save(); show(); };
$("verdict").onsubmit = e => { e.preventDefault(); const f = e.target, a = ans[DATA[i].case];
  if (!f.leak.value) return alert("Answer the leak question first.");
  Object.assign(a, { leak: f.leak.value, over: f.over.value, notes: f.notes.value }); save();
  if (i < DATA.length - 1) i++; show(); };
$("prev").onclick = () => { if (i > 0) { i--; show(); } };
$("next").onclick = () => { if (i < DATA.length - 1) { i++; show(); } };
$("dl").onclick = () => { const b = new Blob([JSON.stringify(Object.values(ans), null, 2)], {type: "application/json"});
  const u = URL.createObjectURL(b), l = document.createElement("a");
  l.href = u; l.download = "blind_review___MODE_____VERSION__.json"; l.click(); URL.revokeObjectURL(u); };
show();
</script></body></html>
"""

if __name__ == "__main__":
    main()
