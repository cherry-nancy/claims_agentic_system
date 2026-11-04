"""Step 2: export an out-of-sample note pool for training the leakage detector.

Same eligibility as the study cohort, excluding every patient in the sample; up to POOL_PER_CELL
notes per (category, SNF vs not) cell. The pool is only used to fit the TF-IDF detector, which is then
scored on the 300 sample notes. Stays local under data/ (gitignored).

Run:  $env:PYTHONPATH="src"; uv run python -m snf_pa.data.leakage_pool
"""
import polars as pl

from . import config as C
from .build_packets import build
from .cohort import NOTE_COLUMNS, build_candidates, connect, eligible_filter

POOL_PER_CELL = 300  # 5 categories x 2 labels x 300 = 3,000 notes


def export_pool(out_path) -> int:
    con = connect()
    build_candidates(con)
    sample = (C.SAMPLE_DIR / "sample_cases.csv").as_posix()
    con.execute(f"""
        create or replace table pool as
        select * from (
            select c.hadm_id, c.subject_id, c.category,
                   (c.discharge_location = 'SKILLED NURSING FACILITY')::INT as label_snf,
                   row_number() over (partition by c.category, c.discharge_location = 'SKILLED NURSING FACILITY'
                                      order by hash(c.hadm_id + {C.SEED})) as rn
            from (select *, row_number() over (partition by subject_id order by hash(hadm_id + {C.SEED})) as srn
                  from cand where {eligible_filter()}) c
            where c.srn = 1
              and c.subject_id not in (select subject_id from read_csv_auto('{sample}'))
        ) where rn <= {POOL_PER_CELL}
    """)
    con.execute(f"""
        copy (
            select n.note_id, n.hadm_id, n.text, p.label_snf, p.category, 'pool' as split
            from read_csv('{C.sql_path(C.NOTE_FILE)}', header=true, quote='"', escape='"', columns={NOTE_COLUMNS}) n
            join pool p using (hadm_id)
        ) to '{C.sql_path(out_path)}' (format parquet)
    """)
    return con.execute(f"select count(*) from read_parquet('{C.sql_path(out_path)}')").fetchall()[0][0]


def main() -> None:
    raw = C.SAMPLE_DIR / "pool_notes_raw.parquet"
    print("pool notes:", export_pool(raw))
    frames, _, report = build(pl.read_parquet(raw))
    frames["all"].write_parquet(C.SAMPLE_DIR / "pool_spans_all.parquet")
    frames["strict"].write_parquet(C.SAMPLE_DIR / "pool_packets_strict.parquet")
    frames["realistic"].write_parquet(C.SAMPLE_DIR / "pool_packets_realistic.parquet")
    print("pool notes with HC:", report["notes_with_section"].get("HC"), "of", report["n_notes"])


if __name__ == "__main__":
    main()
