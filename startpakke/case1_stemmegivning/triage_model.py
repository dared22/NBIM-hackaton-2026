"""Scores how likely NBIM is to vote MOT, from past votes and basic proposal fields. No LLM.

This decides what gets flagged and what goes to a person. Jev explains the result.

Every history feature uses strictly earlier meetings. The model for a year trains on
earlier years only, and its review thresholds come from earlier years too, so nothing
from the scored year sets them.

    python triage_model.py --year 2025     # score a year and show how it does
"""

import argparse
from collections import defaultdict
from dataclasses import dataclass

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score

from jev_mvp import VOTE_OPTIONS, is_eligible, item_key, load_votes, mot_metrics

CATEGORICAL = ("proposal_type", "market", "proponent", "mgmt_rec")
COUNTS = (
    "company_votes", "company_mot", "company_type_votes", "company_type_mot",
    "item_votes", "item_mot", "country_type_votes", "country_type_mot", "type_votes", "type_mot",
)
FEATURES = (*CATEGORICAL, "country", *COUNTS, "last_meeting_mot", "items_in_meeting", "text_length")
SEEDS = 3
THRESHOLD_YEARS = 3  # Thresholds are chosen on this many earlier years, pooled.
TARGET_RECALL = 0.9  # low: scores below this are not reviewed. Keeps this share of MOT votes.
TARGET_PRECISION = 0.8  # high: automatic MOT should be right at least this often.


def groups_for(row):
    """The history a row draws on, one key per pair of counts in COUNTS."""
    return (
        ("company", row["company_id"]),
        ("company_type", row["company_id"], row["proposal_type"]),
        ("item", row["company_id"], item_key(row)),
        ("country_type", row["country"], row["proposal_type"]),
        ("type", row["proposal_type"]),
    )


def build_features(rows):
    """One feature row per input row. Rows must already have a valid NBIM vote.

    Votes are only added to the history after their whole meeting date has passed,
    so a row can never see its own meeting or another one held the same day.
    """
    codes = {c: {v: i for i, v in enumerate(sorted({r[c] for r in rows}))} for c in (*CATEGORICAL, "country")}
    items_in_meeting = defaultdict(int)
    for r in rows:
        items_in_meeting[r["meeting_id"]] += 1

    order = sorted(range(len(rows)), key=lambda i: rows[i]["meeting_date"])
    history = defaultdict(lambda: [0, 0])
    last_meeting = {}
    out = np.zeros((len(rows), len(FEATURES)))
    start = 0
    while start < len(order):
        date = rows[order[start]]["meeting_date"]
        end = start
        while end < len(order) and rows[order[end]]["meeting_date"] == date:
            end += 1
        batch = order[start:end]
        for i in batch:
            r = rows[i]
            counts = [n for key in groups_for(r) for n in history[key]]
            out[i] = [
                *(codes[c][r[c]] for c in CATEGORICAL), codes["country"][r["country"]], *counts,
                last_meeting.get(r["company_id"], -1), items_in_meeting[r["meeting_id"]], len(r["proposal_text"]),
            ]
        mot_this_date = defaultdict(int)
        for i in batch:
            r = rows[i]
            mot = r["nbim_vote"] == "MOT"
            for key in groups_for(r):
                history[key][0] += 1
                history[key][1] += mot
            mot_this_date[r["company_id"]] += mot
        last_meeting.update(mot_this_date)
        start = end
    return out


def fit_and_score(X, y, train, score):
    """Average of a few fits, because MOT votes are rare and one fit is noisy."""
    categorical = [FEATURES.index(c) for c in CATEGORICAL]
    total = np.zeros(score.sum())
    for seed in range(SEEDS):
        model = HistGradientBoostingClassifier(
            max_iter=200, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=20,
            l2_regularization=1.0, categorical_features=categorical, random_state=seed,
        )
        total += model.fit(X[train], y[train]).predict_proba(X[score])[:, 1]
    return total / SEEDS


def choose_thresholds(scores, actual):
    """low keeps TARGET_RECALL of MOT votes. flag has the best F1. high is the first score reaching TARGET_PRECISION.

    Below low: FOR, unreviewed. From flag up: recommend MOT. From high up: MOT without review.
    On 2022-2024 held out, precision reached 80% only at the very top, so high rarely fires
    and people see almost every recommended MOT. That is what the evidence supports.
    """
    grid = np.unique(scores)
    low = max(t for t in grid if actual[scores >= t].sum() >= TARGET_RECALL * actual.sum())
    flag = max(grid, key=lambda t: mot_metrics(list(scores >= t), list(actual))["f1"])
    high = next((t for t in grid if t >= low and actual[scores >= t].mean() >= TARGET_PRECISION), None)
    return float(low), float(flag), float(high) if high is not None else float("inf")


@dataclass
class Triage:
    scores: dict  # (meeting_id, item_no) -> p(MOT)
    low: float
    flag: float
    high: float

    def for_row(self, row):
        return {"p_model": self.scores[row["meeting_id"], row["item_no"]], "low": self.low, "flag": self.flag, "high": self.high}


def score_year(rows, year):
    """Scores for every voted row in a year, using only earlier years to train and set thresholds."""
    voted = [r for r in rows if r["nbim_vote"] in VOTE_OPTIONS]
    years = np.array([int(r["year"]) for r in voted])
    X, y = build_features(voted), np.array([r["nbim_vote"] == "MOT" for r in voted])

    earlier = [t for t in range(year - THRESHOLD_YEARS, year) if (years < t).any() and (years == t).any()]
    if not earlier:
        raise SystemExit(f"The triage model needs at least two earlier years of votes to score {year}.")
    held_out = [(fit_and_score(X, y, years < t, years == t), y[years == t]) for t in earlier]
    low, flag, high = choose_thresholds(np.concatenate([s for s, _ in held_out]), np.concatenate([a for _, a in held_out]))

    target = years == year
    scores = fit_and_score(X, y, years < year, target)
    keys = [(r["meeting_id"], r["item_no"]) for r, t in zip(voted, target) if t]
    return Triage(dict(zip(keys, map(float, scores))), low, flag, high)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--year", type=int, required=True)
    a = p.parse_args()

    rows = load_votes()
    triage = score_year(rows, a.year)
    picked = [r for r in rows if r["year"] == str(a.year) and is_eligible(r)]
    scores = np.array([triage.scores[r["meeting_id"], r["item_no"]] for r in picked])
    actual = [r["nbim_vote"] == "MOT" for r in picked]

    print(f"{a.year}: {len(picked)} proposals, {sum(actual)} MOT. Thresholds from earlier years: low {triage.low:.3f}, flag {triage.flag:.3f}, high {triage.high:.3f}.")
    print(f"Average precision {average_precision_score(actual, scores):.3f} (base rate {np.mean(actual):.3f})")
    flagged = mot_metrics(list(scores >= triage.flag), actual)
    print(f"Recommended MOT:  precision {flagged['precision']:.1%}  recall {flagged['recall']:.1%}  F1 {flagged['f1']:.1%}  hits {flagged['tp']}  false alarms {flagged['fp']}")
    print(f"Automatic MOT:    {(scores >= triage.high).sum()} proposals")
    kept = mot_metrics(list(scores >= triage.low), actual)
    review = ((scores >= triage.low) & (scores < triage.high)).mean()
    print(f"Sent to a person: {review:.1%} of proposals. Above low: recall {kept['recall']:.1%}, so {kept['fn']} MOT votes pass unreviewed.")


if __name__ == "__main__":
    main()
