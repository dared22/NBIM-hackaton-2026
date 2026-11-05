"""Fit how Jev, the triage model and the proposal's record combine, on one or more development years.

Writes data/combination.json: the weights, the share of proposals to review, the triage
model's flag and the Jev level the answers came from. Pooling several years gives a steadier
review share than one year: a single year with a surprise (Kinder Morgan in 2023) can move it a lot.

The share is the one that reaches TARGET_RECALL of the pooled years' MOT votes, scored by
companies the fit did not see. The flag is chosen by the triage model on years before the
last fitted year. Never fit on a holdout.

    python src/fit_combination.py --years 2021 2022 2023 2024 2025 --tag _v6
"""

import argparse
import csv
import json

import numpy as np
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold

from jev_mvp import COMBINATION, RUNS, build_history_index, combination_features, load_votes
from triage_model import TARGET_RECALL, score_year

C = 0.3  # Light regularisation: rare proposal types have very few MOT votes.


def fit(years, rows=None, tag="_v6", level="history", triage=None):
    """The combination fitted on these years, as a dict. Nothing is written.

    triage: optional {year: Triage}, to avoid retraining the triage model for every fit.
    """
    years = sorted(years)
    rows = rows or load_votes()
    by_key = {(r["meeting_id"], r["item_no"]): r for r in rows}
    index = build_history_index(rows)
    triage = triage or {}
    features, y, companies = [], [], []
    for year in years:
        scores = (triage.get(year) or score_year(rows, year)).scores
        with open(RUNS / f"results_{year}_{level}{tag}.csv", encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                row = by_key[r["meeting_id"], r["item_no"]]
                features.append(combination_features(row, float(r["p_mot"]), scores[r["meeting_id"], r["item_no"]], index))
                y.append(row["nbim_vote"] == "MOT")
                companies.append(row["company_id"])
    vectorizer = DictVectorizer(sparse=False)
    X = vectorizer.fit_transform(features)
    y = np.array(y)

    held_out = np.zeros(len(y))
    for train, test in GroupKFold(5).split(X, y, companies):
        held_out[test] = LogisticRegression(C=C, max_iter=3000).fit(X[train], y[train]).predict_proba(X[test])[:, 1]
    cutoff = max(t for t in np.unique(held_out) if y[held_out >= t].sum() >= TARGET_RECALL * y.sum())

    model = LogisticRegression(C=C, max_iter=3000).fit(X, y)
    flag = (triage.get(years[-1]) or score_year(rows, years[-1])).flag
    return {
        "fitted_on": years,
        "level": level,
        "results": f"data/jev_runs/results_<year>_{level}{tag}.csv",
        "target_recall": TARGET_RECALL,
        "review_share": round(float((held_out >= cutoff).mean()), 4),
        "model_flag": round(flag, 4),
        "intercept": round(float(model.intercept_[0]), 4),
        "weights": {k: round(float(w), 4) for k, w in zip(vectorizer.get_feature_names_out(), model.coef_[0])},
    }


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--years", type=int, nargs="+", required=True)
    p.add_argument("--tag", default="_v7", help="which saved Jev runs to read")
    p.add_argument("--level", default="history")
    a = p.parse_args()
    combination = fit(a.years, tag=a.tag, level=a.level)
    COMBINATION.write_text(json.dumps(combination, indent=2) + "\n", encoding="utf-8")
    print(f"Fitted on {a.years} ({a.level} level): review the top {combination['review_share']:.1%}, "
          f"model flag {combination['model_flag']}. Wrote {COMBINATION.relative_to(COMBINATION.parents[1])}.")


if __name__ == "__main__":
    main()
