"""Run medgemma:4b on one real (redacted) MIMIC discharge summary.

Privacy: note text is NEVER printed. Full output goes to traces/ (gitignored);
the terminal only gets counts / booleans.
"""
import json
import re
import sys
import time
from pathlib import Path
from typing import Literal

import duckdb
from langchain_ollama import ChatOllama
from pydantic import BaseModel, Field

H = "data/mimiciv-3.1/hosp"
NOTE_FILE = "data/mimic-iv-note/note/discharge.csv.gz"
OUT = Path("traces/real_case_medgemma.json")

# 1. pick one Medicare, hip-fracture (ICD-10 S72), SNF-discharged case; deterministic
HADM = duckdb.sql(f"""
    select a.hadm_id
    from read_csv_auto('{H}/admissions.csv.gz') a
    join (select distinct hadm_id from read_csv_auto('{H}/diagnoses_icd.csv.gz')
          where icd_version = 10 and icd_code like 'S72%') d using (hadm_id)
    where a.insurance = 'Medicare' and a.discharge_location = 'SKILLED NURSING FACILITY'
      and date_diff('day', a.admittime::date, a.dischtime::date) between 4 and 10
    order by hash(a.hadm_id) limit 1
""").fetchall()[0][0]

adm = duckdb.sql(f"""
    select admission_type, admission_location,
           date_diff('day', admittime::date, dischtime::date) as midnights
    from read_csv_auto('{H}/admissions.csv.gz') where hadm_id = {HADM}
""").fetchall()[0]

t = time.time()
raw = duckdb.sql(f"""
    select text from read_csv('{NOTE_FILE}', header=true, quote='"', escape='"',
        columns={{'note_id':'VARCHAR','subject_id':'BIGINT','hadm_id':'BIGINT','note_type':'VARCHAR',
                 'note_seq':'INT','charttime':'VARCHAR','storetime':'VARCHAR','text':'VARCHAR'}})
    where hadm_id = {HADM}
""").fetchall()[0][0]
print(f"hadm picked: admission_type={adm[0]}, from={adm[1]}, midnights={adm[2]}; "
      f"note loaded {len(raw)} chars in {time.time() - t:.0f}s")

# 2. redact: drop disposition / instructions / follow-up sections + any destination wording
DROP = ("Discharge Disposition", "Facility", "Discharge Instructions", "Followup Instructions")
HEAD = re.compile(r"^[A-Z][A-Za-z /&\-]{2,40}:\s*$", re.M)
marks = list(HEAD.finditer(raw))
keep, last = [], 0
for i, m in enumerate(marks):
    end = marks[i + 1].start() if i + 1 < len(marks) else len(raw)
    if m.group(0).strip().rstrip(":") in DROP:
        keep.append(raw[last:m.start()])
        last = end
keep.append(raw[last:])
red = "".join(keep)
LEAK = re.compile(r"skilled nursing|\bSNF\b|rehab|extended care|nursing (home|facility)|\bfacility\b|discharged? to", re.I)
red_lines = [ln for ln in red.splitlines() if not LEAK.search(ln)]
red = "\n".join(red_lines)
print(f"redacted: {len(raw)} -> {len(red)} chars; leak-pattern hits remaining: {len(LEAK.findall(red))}")


class Criterion(BaseModel):
    finding: str
    verbatim_quote: str


class Review(BaseModel):
    primary_diagnosis: str
    skilled_needs: list[Criterion] = Field(max_length=5)
    functional_status: list[Criterion] = Field(max_length=5)
    meets_daily_skilled_need: Literal["yes", "no", "insufficient_information"]
    qualifies_for_snf: Literal["yes", "no", "insufficient_information"]
    rationale: str


PROMPT = """You are a utilization-review nurse screening a Medicare patient for skilled nursing facility (SNF) coverage.
Use ONLY the discharge summary below. Medicare SNF coverage needs: a qualifying 3-day inpatient stay (already verified),
a need for DAILY skilled nursing or skilled rehabilitation, related to the hospital condition, that as a practical matter
can only be given in a SNF. For every finding give a short VERBATIM quote copied exactly from the note.
If the note does not say, use "insufficient_information". Do not invent facts.
List at most 5 DISTINCT items per list; never repeat a finding. Keep the rationale under 80 words.

DISCHARGE SUMMARY:
{note}
"""

MODEL = sys.argv[1] if len(sys.argv) > 1 else "medgemma:4b"
small_ctx = "meditron" in MODEL  # Llama-2 base: 4k context window
extra = {"reasoning": False} if "qwen3" in MODEL else {}  # no <think> block: slower, breaks JSON
llm = ChatOllama(model=MODEL, temperature=0, num_ctx=4096 if small_ctx else 12288,
                 num_predict=1000 if small_ctx else 1500, repeat_penalty=1.15, **extra)
OUT = Path(f"traces/real_case_{MODEL.replace(':', '_')}.json")
print(f"model: {MODEL}")
t = time.time()
try:
    res = llm.with_structured_output(Review).invoke(PROMPT.format(note=red))
except Exception as e:  # never print e: it can contain note text
    print(f"FAILED after {time.time() - t:.0f}s: {type(e).__name__} (output not shown, may contain note text)")
    raise SystemExit(1)
dt = time.time() - t

# 3. verify every quote really exists in the note (whitespace-normalised)
norm = lambda s: re.sub(r"\s+", " ", s).lower().strip()
nn = norm(red)
quotes = [c.verbatim_quote for c in res.skilled_needs + res.functional_status]
ok = [norm(q) in nn for q in quotes if q.strip()]

OUT.parent.mkdir(exist_ok=True)
OUT.write_text(json.dumps({"hadm_id": int(HADM), "result": res.model_dump(), "quotes_found": ok}, indent=2), encoding="utf-8")

print(f"model time: {dt:.0f}s")
print(f"skilled_needs={len(res.skilled_needs)}, functional_status={len(res.functional_status)}")
print(f"meets_daily_skilled_need={res.meets_daily_skilled_need}, qualifies_for_snf={res.qualifies_for_snf}")
print(f"quotes verified verbatim: {sum(ok)}/{len(ok)}")
print(f"full output (read it in your IDE): {OUT}")
