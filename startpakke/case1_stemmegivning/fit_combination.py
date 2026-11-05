"""Fit how Jev and the triage model combine, on a development year. Prints the constants for jev_mvp.py.

Keep the output in COMBINED_WEIGHTS, REVIEW_LOW and MODEL_FLAG. Never fit this on a holdout.

    python fit_combination.py --year 2025 --results jev_runs/results_2025_history_v3.csv
"""

import argparse
import csv

import numpy as np
from sklearn.linear_model import LogisticRegression

from jev_mvp import load_votes
from triage_model import TARGET_RECALL, score_year


def logit(p):
    p = np.clip(p, 1e-3, 1 - 1e-3)
    return np.log(p / (1 - p))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--year", type=int, required=True)
    p.add_argument("--results", required=True, help="a full run for that year, for Jev's p(MOT)")
    a = p.parse_args()

    with open(a.results, encoding="utf-8", newline="") as f:
        results = list(csv.DictReader(f))
    triage = score_year(load_votes(), a.year)
    jev = np.array([float(r["p_mot"]) for r in results])
    model = np.array([triage.scores[r["meeting_id"], r["item_no"]] for r in results])
    actual = np.array([r["nbim_vote"] == "MOT" for r in results])

    fit = LogisticRegression().fit(np.c_[logit(jev), logit(model)], actual)
    combined = fit.predict_proba(np.c_[logit(jev), logit(model)])[:, 1]
    low = max(t for t in np.unique(combined) if actual[combined >= t].sum() >= TARGET_RECALL * actual.sum())

    print(f'COMBINED_WEIGHTS = {{"jev": {fit.coef_[0][0]:.3f}, "model": {fit.coef_[0][1]:.3f}, "intercept": {fit.intercept_[0]:.3f}}}')
    print(f"REVIEW_LOW = {low:.3f}")
    print(f"MODEL_FLAG = {triage.flag:.3f}")


if __name__ == "__main__":
    main()
