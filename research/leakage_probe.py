"""Third leakage check (design §3.5): TF-IDF + logistic regression predicting "discharged to SNF" from note text.

    uv run python research/leakage_probe.py

DEV ADMISSIONS ONLY (hard rule 3; split by hadm_id, design v9): dev admissions in the candidate pool, excluding
the frozen dev sample. 2,000 SNF + 2,000 non-SNF (HHC / HOME) admissions, fixed seed. 5-fold GroupKFold by
subject_id so one patient's admissions never sit on both sides of a fold; out-of-fold AUC, bootstrap 95% CI.

Variants:
  raw            full original note
  redacted       what enters the CaseBundle (discharge_note.to_evidence)
  redacted_noPA  redacted minus any kept sentence with a destination word outside the discharge-time sections
                 (pre-admission residence / rehab history) - sensitivity analysis only, not the system input

Writes data/derived/probe/leakage_probe.json (not in git). Prints aggregates only.
"""
from __future__ import annotations

import json
import time

import duckdb
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold

from snf_pa.adapters.sources import discharge_note as dn
from snf_pa.paths import ROOT

N_PER_CLASS = 2000
SEED = 20261108
OUT = ROOT / "data" / "derived" / "probe"


def load_rows():
    con = duckdb.connect()
    return con.execute(f"""
        with cand as (
            select p.hadm_id, p.subject_id, (p.discharge_location = 'SKILLED NURSING FACILITY')::int as y, d.text
            from '{(ROOT / "data/derived/cohort/pool.parquet").as_posix()}' p
            join read_csv('{(ROOT / "data/splits/admissions.csv").as_posix()}') s on s.hadm_id = p.hadm_id
            join '{(ROOT / "data/derived/parquet/discharge.parquet").as_posix()}' d on d.hadm_id = p.hadm_id
            where s.split = 'dev'
              and p.hadm_id not in (select hadm_id from read_csv('{(ROOT / "data/splits/dev_cases.csv").as_posix()}'))
        )
        select * from cand qualify row_number() over (partition by y order by hash(hadm_id + {SEED})) <= {N_PER_CLASS}
        order by hadm_id""").fetchall()


def variants(text: str) -> dict[str, str]:
    spans = dn.index_note(text)
    kept, _ = dn.redact(spans)
    broad = dn.broad_sections(spans)
    no_pa = [s for s in kept if s.section in broad or not dn.PLACE_SNF.search(s.text)]
    return {"raw": text, "redacted": "\n".join(s.text for s in kept), "redacted_noPA": "\n".join(s.text for s in no_pa)}


def oof_auc(texts, y, groups):
    oof = np.zeros(len(y))
    for tr, te in GroupKFold(n_splits=5).split(texts, y, groups):
        vec = TfidfVectorizer(ngram_range=(1, 2), min_df=5, max_features=50000, sublinear_tf=True)
        xtr = vec.fit_transform([texts[i] for i in tr])
        clf = LogisticRegression(C=1.0, max_iter=2000).fit(xtr, y[tr])
        oof[te] = clf.predict_proba(vec.transform([texts[i] for i in te]))[:, 1]
    rng = np.random.default_rng(SEED)
    boots = []
    for _ in range(1000):
        idx = rng.integers(0, len(y), len(y))
        if y[idx].min() != y[idx].max():
            boots.append(roc_auc_score(y[idx], oof[idx]))
    return roc_auc_score(y, oof), np.percentile(boots, [2.5, 97.5]).tolist()


def top_features(texts, y, k=25):
    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=5, max_features=50000, sublinear_tf=True)
    x = vec.fit_transform(texts)
    coef = LogisticRegression(C=1.0, max_iter=2000).fit(x, y).coef_[0]
    names = np.array(vec.get_feature_names_out())
    order = np.argsort(coef)
    return {"toward_snf": names[order[::-1][:k]].tolist(), "toward_not_snf": names[order[:k]].tolist()}


def main() -> None:
    t0 = time.time()
    rows = load_rows()
    y = np.array([r[2] for r in rows])
    groups = np.array([r[1] for r in rows])
    v = [variants(r[3]) for r in rows]
    result = {"n": len(rows), "n_snf": int(y.sum()), "seed": SEED, "population": "dev admissions (split by hadm_id), pool SNF/HHC/HOME, not in dev sample",
              "auc": {}, "top_features": {}}
    for name in ("raw", "redacted", "redacted_noPA"):
        auc, ci = oof_auc([x[name] for x in v], y, groups)
        result["auc"][name] = {"auc": round(auc, 3), "ci95": [round(c, 3) for c in ci]}
        print(f"{name:14s} AUC {auc:.3f}  95% CI [{ci[0]:.3f}, {ci[1]:.3f}]", flush=True)
    for name in ("redacted",):
        result["top_features"][name] = top_features([x[name] for x in v], y)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "leakage_probe.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("top features (redacted):", json.dumps(result["top_features"]["redacted"], indent=1))
    print(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
