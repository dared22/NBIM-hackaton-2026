"""models.history: NBIM voting decision support."""

import collections
import csv
import re

from src.models import scoring
from src.models.scoring import fit_logistic, predict

# Smoothing strength: how many "virtual" votes the broader average counts for.
M = 8.0
# History inputs are capped at +/- CLIP so one company with an extreme record
# (hundreds of items in one year) cannot dominate. Chosen on test years 2022-2025.
CLIP = 1.0
# Below LOW the proposal goes in the "likely WITH board" band. 5% is NBIM's overall
# rate of voting against the board, so this means "below-average risk".
LOW = 0.05

FEATURES = [
    ("type", "how often NBIM opposes this proposal type"),
    ("type_country", "this proposal type in this country"),
    ("company", "NBIM's history of opposing this company"),
    ("company_type", "this proposal type at this company"),
    ("text", "this exact proposal wording, across companies"),
    ("same_item_against", "NBIM opposed this same item at this company last time"),
    ("same_item_for", "NBIM supported this same item at this company last time"),
    ("first_meeting", "no earlier meetings for this company in the data"),
]


def read_votes(path):
    """Rows with a known board recommendation and NBIM vote, oldest first."""
    with open(path, encoding="utf-8", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["against_board"] in ("0.0", "1.0")]
    for r in rows:
        r["y"] = 1 if r["against_board"] == "1.0" else 0
        r["text_key"] = re.sub(r"[^a-z0-9]+", " ", r["proposal_text"].lower()).strip()
    rows.sort(key=lambda r: (r["meeting_date"], r["meeting_id"], r["item_no"]))
    return rows


def cap(v):
    return max(-CLIP, min(CLIP, v))


def add_history_features(rows, history_before=None):
    """Attach features computed only from meetings on earlier dates.

    All rows from one date are scored before any of them are added to the
    history, so a meeting can never see its own outcome. When history_before is
    set, outcomes on or after that date are never added to history.
    """
    counts = collections.defaultdict(lambda: [0, 0])  # key -> [votes, against]
    last_vote = {}  # (company, text) -> last outcome
    seen_company = set()

    def rate(key, prior):
        n, k = counts[key]
        return (k + M * prior) / (n + M)

    by_date = collections.defaultdict(list)
    for r in rows:
        by_date[r["meeting_date"]].append(r)

    for date in sorted(by_date):
        todays = by_date[date]
        for r in todays:
            c, t, land, txt = r["company_id"], r["proposal_type"], r["country"], r["text_key"]
            p_all = rate("all", 0.05)
            p_type = rate(("type", t), p_all)
            p_tc = rate(("tc", t, land), p_type)
            p_comp = rate(("comp", c), p_all)
            p_ct = rate(("ct", c, t), p_tc)
            p_text = rate(("text", txt), p_type)
            prev = last_vote.get((c, txt))
            r["x"] = [
                cap(scoring.logit(p_type)),
                cap(scoring.logit(p_tc) - scoring.logit(p_type)),
                cap(scoring.logit(p_comp) - scoring.logit(p_all)),
                cap(scoring.logit(p_ct) - scoring.logit(p_tc)),
                cap(scoring.logit(p_text) - scoring.logit(p_type)),
                1.0 if prev == 1 else 0.0,
                1.0 if prev == 0 else 0.0,
                0.0 if c in seen_company else 1.0,
            ]
            r["prev_same_item"] = prev
        if history_before is not None and date >= history_before:
            continue
        for r in todays:
            c, t, land, txt, y = (
                r["company_id"],
                r["proposal_type"],
                r["country"],
                r["text_key"],
                r["y"],
            )
            for key in (
                "all",
                ("type", t),
                ("tc", t, land),
                ("comp", c),
                ("ct", c, t),
                ("text", txt),
            ):
                counts[key][0] += 1
                counts[key][1] += y
            last_vote[(c, txt)] = y
            seen_company.add(c)


def reasons(w, x, top=2):
    """The inputs that pushed this score up the most, in plain words."""
    parts = sorted(((wi * xi, text) for wi, xi, (_, text) in zip(w[1:], x, FEATURES)), reverse=True)
    return "; ".join(text for value, text in parts[:top] if value > 0.05)


def run_year(rows, test_year):
    """Fit on earlier years, score the test year. Returns (train, test, weights, threshold)."""

    def year(r):
        return int(r["meeting_date"][:4])

    train = [r.copy() for r in rows if year(r) < test_year]
    test = [r.copy() for r in rows if year(r) == test_year]
    add_history_features(train + test, f"{test_year}-01-01")
    # The threshold is chosen on the last training year, by a model that never saw it.
    fit_part = [r for r in train if year(r) < test_year - 1]
    val_part = [r.copy() for r in train if year(r) == test_year - 1]
    add_history_features(fit_part + val_part, f"{test_year - 1}-01-01")
    w_val = fit_logistic([r["x"] for r in fit_part], [r["y"] for r in fit_part])
    threshold = scoring.best_f1_threshold(
        [predict(w_val, r["x"]) for r in val_part], [r["y"] for r in val_part]
    )
    w = fit_logistic([r["x"] for r in train], [r["y"] for r in train])
    for r in test:
        r["p"] = predict(w, r["x"])
        r["band"] = (
            "likely AGAINST board"
            if r["p"] >= threshold
            else "likely WITH board"
            if r["p"] < LOW
            else "send to human"
        )
    return train, test, w, threshold
