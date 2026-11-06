"""Leakage audit of the redacted notes: can the discharge destination still be read from them?

Run from the project root (after snf_pa.data.redact):
    PYTHONPATH=src uv run python -m snf_pa.data.leakage

A text classifier (TF-IDF + logistic regression) is trained on a separate pool of candidate notes and tested on the
sample, SNF vs HOME / HOME HEALTH CARE (IRF cases are left out, as in the plan's P/R/F1). With 420 sample notes,
cross-validated AUCs move by about 0.05, too much to compare redaction versions; the pool gives a stable estimate.
It is compared with a classifier on structured fields only (age, midnights, ICU, category, sex). Redacted notes
should land near that baseline: the rest of the gap is clinical signal (function, cognition, wounds) that a reviewer
is meant to use, which the top terms show.

The pool: candidates (snf_pa.data.cohort) whose patient is in neither sample file, POOL_PER_CLASS SNF and
POOL_PER_CLASS home / home health admissions drawn in seeded hash order. Its notes are exported once to
data/sample/notes_pool.parquet (gitignored; building it scans the 1.1 GB note file).

Writes data/sample/leakage_report.json. Output is aggregate only: AUCs, per-group term rates, and model terms
that occur in at least MIN_DF notes. Never note text.
"""
import json
import re

import numpy as np
import polars as pl
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from snf_pa.data import cohort
from snf_pa.data import config as C
from snf_pa.data.redact import FILES, MODES, VERSION, redact

POOL_PER_CLASS = 1500
MIN_DF = 20
POOL_CASES = C.SAMPLE_DIR / "pool_cases.parquet"
POOL_NOTES = C.SAMPLE_DIR / "notes_pool.parquet"
REPORT = C.SAMPLE_DIR / "leakage_report.json"
SAMPLES = ["sample_cases1", "sample_cases1_supp"]
HOME = ("HOME", "HOME HEALTH CARE")

# Residual disposition terms: the share of notes with each, by destination, before and after redaction.
TERMS = {"rehab": r"(?i)\brehab", "facility": r"(?i)\bfacilit", "SNF/nursing home": r"(?i)\bSNF\b|nursing (home|facility)|extended care",
         "home with": r"(?i)home (with|w/)", "VNA/home health": r"(?i)\bVNA\b|home health|visiting nurse|home (PT|services)",
         "discharg* to/home": r"(?i)discharg\w*\s+(to|home)", "dispo": r"(?i)\bdispo", "placement": r"(?i)placement",
         "Refills/RX/Disp #": r"Refills:|\bRX \*|Disp #", "screen": r"(?i)\bscreen", "accepted": r"(?i)\baccept",
         "case manag/social work": r"(?i)case manag|social work|\bSW\b", "PCP": r"\bPCP\b",
         "PT recommend": r"(?i)\b(PT|OT|physical therapy)\b.{0,40}\brecommend"}


def build_pool() -> None:
    used = pl.concat([pl.read_csv(C.SAMPLE_DIR / f"{f}.csv", infer_schema_length=0).select("subject_id")
                      for f in SAMPLES])["subject_id"].to_list()
    con = cohort.connect()
    print("building candidate pool (scans the 1.1 GB note file)...")
    cohort.build_candidates(con)
    con.execute("create or replace temp table used as select unnest(?::VARCHAR[]) as subject_id", [used])
    pool = con.sql(f"""
    select subject_id, hadm_id, note_id, category, discharge_location, age_at_admit, gender,
           inpatient_midnights, icu_any as had_icu, label_snf
    from candidates
    where subject_id::VARCHAR not in (select subject_id from used)
    qualify row_number() over (partition by label_snf order by md5(hadm_id::VARCHAR || ':pool:{C.SEED}'))
            <= {POOL_PER_CLASS}
    """).pl()
    pool.write_parquet(POOL_CASES)
    print("exporting pool notes...")
    cohort.export_notes(con, pool["note_id"].cast(pl.String).to_list(), POOL_NOTES)


def sample_frame() -> pl.DataFrame:
    cols = ["hadm_id", "discharge_location", "category", "age_at_admit", "inpatient_midnights", "had_icu",
            "gender"]
    cases = pl.concat([pl.read_csv(C.SAMPLE_DIR / f"{f}.csv", infer_schema_length=0).select(cols).with_columns(
        source=pl.lit(f)) for f in SAMPLES])
    raw = pl.concat([pl.read_parquet(C.SAMPLE_DIR / f"{f}.parquet").select("hadm_id", "text") for f in FILES])
    red = pl.concat([pl.read_parquet(C.SAMPLE_DIR / f"{f}.parquet") for f in FILES.values()])
    assert (red["redaction_version"] == VERSION).all(), "rerun snf_pa.data.redact first"
    red = red.pivot(on="mode", index="hadm_id", values="text")
    return (raw.rename({"text": "raw"}).join(red, on="hadm_id").with_columns(pl.col("hadm_id").cast(pl.String))
            .join(cases, on="hadm_id"))


def pool_frame() -> pl.DataFrame:
    notes = pl.read_parquet(POOL_NOTES).select("hadm_id", pl.col("text").alias("raw"))
    notes = notes.with_columns(*[pl.col("raw").map_elements(lambda t, m=m: redact(t, m)[0], return_dtype=pl.String)
                                 .alias(m) for m in MODES])
    cases = pl.read_parquet(POOL_CASES).with_columns(pl.col(c).cast(pl.String) for c in
                                                     ["hadm_id", "age_at_admit", "inpatient_midnights", "had_icu"])
    return notes.with_columns(pl.col("hadm_id").cast(pl.String)).join(cases, on="hadm_id")


def structured(train: pl.DataFrame, test: pl.DataFrame) -> np.ndarray:
    def num(d):
        return np.column_stack([d["age_at_admit"].cast(pl.Float64), d["inpatient_midnights"].cast(pl.Float64),
                                d["had_icu"].str.to_lowercase() == "true"])
    sc = StandardScaler().fit(num(train))
    oh = OneHotEncoder(handle_unknown="ignore").fit(train.select("category", "gender").to_numpy())
    x = [np.column_stack([sc.transform(num(d)), oh.transform(d.select("category", "gender").to_numpy()).toarray()])
         for d in (train, test)]
    lr = LogisticRegression(max_iter=2000).fit(x[0], train["y"])
    return lr.predict_proba(x[1])[:, 1]


def text_model(train: list[str], y: np.ndarray):
    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=MIN_DF, sublinear_tf=True,
                          token_pattern=r"(?u)\b[A-Za-z][A-Za-z]+\b")
    lr = LogisticRegression(C=1.0, max_iter=2000).fit(vec.fit_transform(train), y)
    return vec, lr


def term_rates(d: pl.DataFrame) -> list[dict]:
    rows = []
    for name, pat in TERMS.items():
        row = {"term": name}
        for (loc,), g in sorted(d.group_by("discharge_location"), key=lambda x: x[0]):
            row[loc] = {col: round(sum(bool(re.search(pat, t)) for t in g[col]) / g.height, 3)
                        for col in ["raw", *MODES]}
        rows.append(row)
    return rows


def main() -> None:
    if not POOL_NOTES.exists():
        build_pool()
    pool = pool_frame().with_columns(y=pl.col("label_snf").cast(pl.Int64))
    sample = sample_frame()
    test = sample.filter(pl.col("discharge_location").is_in(["SKILLED NURSING FACILITY", *HOME])).with_columns(
        y=(pl.col("discharge_location") == "SKILLED NURSING FACILITY").cast(pl.Int64))
    y_train, y_test = pool["y"].to_numpy(), test["y"].to_numpy()
    main_rows = (test["source"] == "sample_cases1").to_numpy()

    def aucs(p):
        return {"all": round(roc_auc_score(y_test, p), 3), "main_sample": round(roc_auc_score(y_test[main_rows], p[main_rows]), 3)}

    report = {"redaction_version": VERSION, "train": {"pool_notes": pool.height, "snf": int(y_train.sum())},
              "test": {"sample_notes": test.height, "snf": int(y_test.sum()), "main_sample": int(main_rows.sum())},
              "auc": {"structured_only": aucs(structured(pool, test))}, "top_terms": {}}
    for col in ["raw", *MODES]:
        vec, lr = text_model(pool[col].to_list(), y_train)
        report["auc"][col] = aucs(lr.predict_proba(vec.transform(test[col].to_list()))[:, 1])
        if col != "raw":
            w, names = lr.coef_[0], vec.get_feature_names_out()
            order = np.argsort(w)
            report["top_terms"][col] = {"snf": names[order[::-1][:25]].tolist(), "home": names[order[:25]].tolist()}
    report["term_rates_sample"] = term_rates(sample)
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"train: {pool.height} pool notes; test: {test.height} sample notes (SNF vs home / home health)")
    print("AUC (all test / main 300-case sample only):")
    for k, v in report["auc"].items():
        print(f"  {k:16s} {v['all']:.3f} / {v['main_sample']:.3f}")
    for col, t in report["top_terms"].items():
        print(f"top terms, {col}:\n  SNF:  {', '.join(t['snf'])}\n  home: {', '.join(t['home'])}")
    print(f"-> {REPORT.relative_to(C.ROOT)}")


if __name__ == "__main__":
    main()
