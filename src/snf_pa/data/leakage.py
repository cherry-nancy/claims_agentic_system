"""Step 2 leakage checks on the packets (aggregate output only).

1. Keyword residue: disposition patterns still present after redaction, by label and section.
2. TF-IDF + logistic regression predicting discharge to SNF from text, repeated stratified CV AUC:
   raw note vs strict vs realistic, whole note and per section; top features of the strict model.
   AUC will not drop to 0.5 (sicker patients go to SNF); the check is that top features are
   clinical, not disposition words, and that no single section carries outsized signal.

Run:  $env:PYTHONPATH="src"; uv run python -m snf_pa.data.leakage
"""
import json
import re
import statistics

import numpy as np
import polars as pl
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import RepeatedStratifiedKFold, cross_val_score
from sklearn.pipeline import make_pipeline

from . import config as C
from .redact import DISPO_STRONG, MASK, PLACE_HOME, PLACE_SNF

SEED = 42
TOKEN = r"(?u)\b[a-zA-Z][a-zA-Z]+\b"  # words only; drops numbers and ___ placeholders


def note_text(spans: pl.DataFrame, section: str | None = None) -> pl.DataFrame:
    if section:
        spans = spans.filter(pl.col("section") == section)
    return spans.group_by("hadm_id").agg(pl.col("text").str.join("\n"))


def with_labels(texts: pl.DataFrame, cases: pl.DataFrame) -> tuple[list[str], np.ndarray]:
    df = cases.join(texts, on="hadm_id", how="left").with_columns(pl.col("text").fill_null(""))
    return df["text"].to_list(), df["label_snf"].to_numpy()


def model() -> object:
    return make_pipeline(
        TfidfVectorizer(token_pattern=TOKEN, ngram_range=(1, 2), min_df=3, sublinear_tf=True, lowercase=True),
        LogisticRegression(C=1.0, max_iter=3000),
    )


def cv_auc(texts: list[str], y: np.ndarray) -> dict:
    cv = RepeatedStratifiedKFold(n_splits=5, n_repeats=5, random_state=SEED)
    try:
        s = cross_val_score(model(), texts, y, cv=cv, scoring="roc_auc", error_score="raise")
    except ValueError:  # section holds no words (e.g. Facility is only '___')
        return {"auc": None, "sd": None}
    return {"auc": round(float(s.mean()), 3), "sd": round(float(s.std()), 3)}


def section_presence(spans: pl.DataFrame, cases: pl.DataFrame) -> dict:
    """Share of notes by label that contain each section; presence itself can leak."""
    have = spans.select("hadm_id", "section").unique()
    out = {}
    for (y,), g in cases.group_by("label_snf"):
        ids = set(g["hadm_id"].to_list())
        cnt = have.filter(pl.col("hadm_id").is_in(ids)).group_by("section").agg(pl.len().alias("n"))
        for r in cnt.iter_rows(named=True):
            out.setdefault(r["section"], {})[f"snf={y}"] = round(r["n"] / len(ids), 3)
    return dict(sorted(out.items()))


def heldout_auc(train: tuple[list[str], np.ndarray], test: tuple[list[str], np.ndarray], n_boot: int = 1000) -> dict:
    """Fit on the out-of-sample pool, score the study sample; bootstrap 95% CI over sample notes."""
    try:
        m = model().fit(*train)
    except ValueError:
        return {"auc": None, "ci95": None}
    p, y = m.predict_proba(test[0])[:, 1], test[1]
    rng = np.random.default_rng(SEED)
    boots = []
    for _ in range(n_boot):
        i = rng.integers(0, len(y), len(y))
        if y[i].min() != y[i].max():
            boots.append(roc_auc_score(y[i], p[i]))
    return {"auc": round(float(roc_auc_score(y, p)), 3),
            "ci95": [round(float(np.percentile(boots, 2.5)), 3), round(float(np.percentile(boots, 97.5)), 3)]}


def top_features(texts: list[str], y: np.ndarray, k: int = 25) -> dict:
    m = model().fit(texts, y)
    vec, lr = m.steps[0][1], m.steps[1][1]
    names = vec.get_feature_names_out()
    order = np.argsort(lr.coef_[0])
    return {"toward_snf": [names[i] for i in order[::-1][:k]], "toward_home": [names[i] for i in order[:k]]}


def residue(spans: pl.DataFrame, cases: pl.DataFrame) -> dict:
    """Notes (by label) whose kept text still matches a disposition pattern, per section."""
    pats = {"place_snf": PLACE_SNF, "place_home": PLACE_HOME, "dispo_strong": DISPO_STRONG}
    lab = dict(zip(cases["hadm_id"].to_list(), cases["label_snf"].to_list()))
    out = {}
    for name, pat in pats.items():
        hits = {}
        for r in spans.iter_rows(named=True):
            t = r["text"].replace(MASK, "")
            if pat.search(t):
                hits.setdefault((r["section"], lab[r["hadm_id"]]), set()).add(r["hadm_id"])
        out[name] = {f"{sec}|snf={y}": len(v) for (sec, y), v in sorted(hits.items())}
    return out


def mask_counts(spans: pl.DataFrame, cases: pl.DataFrame) -> dict:
    per = spans.group_by("hadm_id").agg(pl.col("text").str.count_matches(re.escape(MASK)).sum().alias("m"))
    df = cases.join(per, on="hadm_id", how="left").with_columns(pl.col("m").fill_null(0))
    return {f"snf={y}": {"mean_masks_per_note": round(statistics.mean(g["m"].to_list()), 2),
                         "share_notes_with_mask": round(float((g["m"] > 0).mean()), 3)}
            for (y,), g in df.group_by("label_snf")}


def main() -> None:
    d = C.SAMPLE_DIR
    cases = pl.read_csv(d / "sample_cases.csv").select("hadm_id", "label_snf").sort("hadm_id")
    packets = {name: pl.read_parquet(d / f"{f}.parquet") for name, f in
               (("raw", "spans_all"), ("strict", "packets_strict"), ("realistic", "packets_realistic"))}
    rep: dict = {"n": cases.height, "n_snf": int(cases["label_snf"].sum())}

    rep["whole_note_auc"] = {k: cv_auc(*with_labels(note_text(v), cases)) for k, v in packets.items()}
    rep["section_auc_raw"] = {}
    rep["section_auc_strict"] = {}
    for sec in sorted(packets["raw"]["section"].unique().to_list()):
        rep["section_auc_raw"][sec] = cv_auc(*with_labels(note_text(packets["raw"], sec), cases))
        if sec in packets["strict"]["section"].unique().to_list():
            rep["section_auc_strict"][sec] = cv_auc(*with_labels(note_text(packets["strict"], sec), cases))
    rep["top_features_raw"] = top_features(*with_labels(note_text(packets["raw"]), cases))
    rep["top_features_strict"] = top_features(*with_labels(note_text(packets["strict"]), cases))

    if (d / "pool_spans_all.parquet").exists():  # built by leakage_pool.py
        pool_cases = (pl.read_parquet(d / "pool_notes_raw.parquet", columns=["hadm_id", "label_snf"])
                      .unique().sort("hadm_id"))
        pool = {name: pl.read_parquet(d / f"pool_{f}.parquet") for name, f in
                (("raw", "spans_all"), ("strict", "packets_strict"), ("realistic", "packets_realistic"))}
        rep["pool"] = {"n": pool_cases.height, "n_snf": int(pool_cases["label_snf"].sum())}
        rep["heldout_whole_note_auc"] = {
            k: heldout_auc(with_labels(note_text(pool[k]), pool_cases), with_labels(note_text(packets[k]), cases))
            for k in pool}
        rep["heldout_section_auc_strict"] = {
            sec: heldout_auc(with_labels(note_text(pool["strict"], sec), pool_cases),
                             with_labels(note_text(packets["strict"], sec), cases))
            for sec in sorted(packets["strict"]["section"].unique().to_list())}
        rep["heldout_section_auc_raw_dropped"] = {
            sec: heldout_auc(with_labels(note_text(pool["raw"], sec), pool_cases),
                             with_labels(note_text(packets["raw"], sec), cases))
            for sec in ("DISPO", "MEDDC", "DXDC", "DCI", "FU", "FAC")}
        rep["top_features_strict_pool"] = top_features(*with_labels(note_text(pool["strict"]), pool_cases))
    rep["section_presence_raw"] = section_presence(packets["raw"], cases)
    rep["section_presence_strict"] = section_presence(packets["strict"], cases)
    rep["residue_strict"] = residue(packets["strict"], cases)
    rep["masks_strict"] = mask_counts(packets["strict"], cases)

    (d / "leakage_report.json").write_text(json.dumps(rep, indent=2))
    print(json.dumps(rep, indent=2))


if __name__ == "__main__":
    main()
