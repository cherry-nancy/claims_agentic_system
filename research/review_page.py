"""Second leakage check (design §3.5): a blind review page of 50 processed discharge notes. Human gate.

    uv run python research/review_page.py            # writes data/derived/review/
    uv run python research/review_page.py score <exported.csv>

DEV ADMISSIONS ONLY (hard rule 3; split by hadm_id, design v9): 25 SNF + 25 non-SNF (HHC / HOME) dev admissions
in the pool, fixed seed, shuffled. The page shows only the processed text (what enters the CaseBundle) and never the
destination. The reviewer marks, per note, whether the destination can be told and which sentence gave it away,
then clicks "Export" to save a CSV. The answer key is written to a separate file the page does not load.
Output stays under data/derived/review/ (not in git).
"""
from __future__ import annotations

import csv
import html
import json
import random
import sys

import duckdb

from snf_pa.adapters.sources import discharge_note as dn
from snf_pa.paths import ROOT

OUT = ROOT / "data" / "derived" / "review"
SEED = 20261108
N_PER_CLASS = 25


def pick():
    con = duckdb.connect()
    return con.execute(f"""
        with cand as (
            select p.hadm_id, p.subject_id, (p.discharge_location = 'SKILLED NURSING FACILITY')::int as y,
                   d.note_id, d.text
            from '{(ROOT / "data/derived/cohort/pool.parquet").as_posix()}' p
            join read_csv('{(ROOT / "data/splits/admissions.csv").as_posix()}') s on s.hadm_id = p.hadm_id
            join '{(ROOT / "data/derived/parquet/discharge.parquet").as_posix()}' d on d.hadm_id = p.hadm_id
            where s.split = 'dev'
        )
        select * from cand qualify row_number() over (partition by y order by hash(hadm_id * 7 + {SEED})) <= {N_PER_CLASS}
    """).fetchall()


PAGE = """<!doctype html><html lang="zh"><head><meta charset="utf-8"><title>去泄漏人工抽查</title>
<style>body{{font:14px/1.5 system-ui,sans-serif;max-width:900px;margin:auto;padding:16px;color:#222}}
.case{{border:1px solid #ccc;border-radius:6px;padding:12px;margin:18px 0}} .sec{{color:#666;font-size:12px;margin-top:8px}}
.sp{{margin:2px 0}} .id{{color:#999;font-size:11px;margin-right:6px}} .q{{background:#f5f5f5;padding:8px;margin-top:10px}}
textarea{{width:100%}} button{{font-size:15px;padding:6px 14px}}</style></head><body>
<h1>去泄漏人工抽查（50 篇）</h1>
<p>每篇是处理后、会进入系统的出院小结。请判断：<b>只看这些文字，能不能看出病人出院去了哪里</b>（SNF，还是回家 / 居家护理）。
凭临床情况推测（例如"髋骨折、需要两人协助"）不算泄漏；<b>文字直接或间接说出了去向安排</b>才算（例如床位、接收机构、随访安排、给病人本人的出院指导）。
看出来的，请把那句话的编号或原文填进依据。全部填完后点最下面的"导出"，把 CSV 文件发给 Claude。</p>
{cases}
<p><button onclick="exportCsv()">导出 CSV</button></p>
<script>
function exportCsv(){{
  const rows=[["review_id","verdict","evidence"]];
  document.querySelectorAll('.case').forEach(c=>{{
    const id=c.dataset.id; const v=(c.querySelector('input[type=radio]:checked')||{{value:''}}).value;
    rows.push([id,v,c.querySelector('textarea').value.replace(/"/g,'""')]);
  }});
  const csv=rows.map(r=>r.map(x=>'"'+x+'"').join(',')).join('\\n');
  const a=document.createElement('a'); a.href=URL.createObjectURL(new Blob(['\\ufeff'+csv],{{type:'text/csv'}}));
  a.download='review_answers.csv'; a.click();
}}
</script></body></html>"""

CASE = """<div class="case" data-id="{rid}"><h3>病例 {rid}</h3>{body}
<div class="q">能看出去向吗？
<label><input type="radio" name="v{rid}" value="cannot"> 看不出</label>
<label><input type="radio" name="v{rid}" value="snf"> 看得出：SNF</label>
<label><input type="radio" name="v{rid}" value="home"> 看得出：回家 / 居家护理</label>
<br>依据（句子编号或原文）：<textarea rows="2"></textarea></div></div>"""


def build() -> None:
    rows = pick()
    random.Random(SEED).shuffle(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    cards, key = [], []
    for i, (h, s, y, nid, text) in enumerate(rows, 1):
        kept, _ = dn.redact(dn.index_note(text))
        body, last = [], None
        for sp in kept:
            if sp.section != last:
                body.append(f'<div class="sec">{html.escape(sp.section)}</div>')
                last = sp.section
            body.append(f'<div class="sp"><span class="id">{html.escape(sp.span_id)}</span>{html.escape(sp.text)}</div>')
        cards.append(CASE.format(rid=i, body="".join(body)))
        key.append({"review_id": i, "hadm_id": h, "note_id": nid, "snf": y})
    (OUT / "review.html").write_text(PAGE.format(cases="\n".join(cards)), encoding="utf-8")
    (OUT / "answer_key.json").write_text(json.dumps(key, indent=1), encoding="utf-8")
    print(f"wrote {OUT / 'review.html'} ({len(cards)} notes: {sum(k['snf'] for k in key)} SNF); key in answer_key.json")


def score(path: str) -> None:
    key = {k["review_id"]: k for k in json.loads((OUT / "answer_key.json").read_text(encoding="utf-8"))}
    with open(path, encoding="utf-8-sig") as f:
        ans = list(csv.DictReader(f))
    told = [a for a in ans if a["verdict"] in ("snf", "home")]
    right = [a for a in told if (a["verdict"] == "snf") == bool(key[int(a["review_id"])]["snf"])]
    print(f"answered {len(ans)}; said 'can tell' on {len(told)}; correct among those {len(right)}")
    for a in told:
        print(f"  case {a['review_id']}: said {a['verdict']}, truth {'snf' if key[int(a['review_id'])]['snf'] else 'not snf'}; "
              f"evidence: {a['evidence']}")


if __name__ == "__main__":
    score(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[1] == "score" else build()
