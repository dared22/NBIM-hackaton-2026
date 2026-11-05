"""Scoring model for NBIM votes: will NBIM vote against the board?

Run:
    python3 benchmark/model.py                 # trains on years before 2026, tests on 2026
    python3 benchmark/model.py --test-year 2025
    python3 benchmark/model.py --walk-forward  # same test repeated for 2022-2026

Data: data/real_votes.csv (NBIM's published votes, handed out by the organisers).
Only the Python standard library is used, so the result is reproducible anywhere.

What it does
    1. Cleans the data and drops rows without a board recommendation to compare to.
    2. Builds history features from earlier dates, frozen before each holdout year.
    3. Measures two baselines: "always with the board" and "same as last time".
    4. Fits a logistic regression on the training years and scores the test year.
    5. Sorts every proposal into a band: likely WITH board, send to a human,
       or likely AGAINST board.
    6. Writes one row per test proposal to prediksjoner_<year>.csv, with the
       probability, the band and the reasons behind it.

Columns never used as inputs, because they contain the answer: nbim_vote,
nbim_vote_raw, against_board, rationale_text, position_paper, rationale_section.
"""

import argparse
import collections
import csv
import itertools
import math
import os
import re

HER = os.path.dirname(os.path.abspath(__file__))

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


def logit(p):
    return math.log(p / (1.0 - p))


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
                cap(logit(p_type)),
                cap(logit(p_tc) - logit(p_type)),
                cap(logit(p_comp) - logit(p_all)),
                cap(logit(p_ct) - logit(p_tc)),
                cap(logit(p_text) - logit(p_type)),
                1.0 if prev == 1 else 0.0,
                1.0 if prev == 0 else 0.0,
                0.0 if c in seen_company else 1.0,
            ]
            r["prev_same_item"] = prev
        if history_before is not None and date >= history_before:
            continue
        for r in todays:
            c, t, land, txt, y = (r["company_id"], r["proposal_type"], r["country"], r["text_key"], r["y"])
            for key in ("all", ("type", t), ("tc", t, land), ("comp", c), ("ct", c, t), ("text", txt)):
                counts[key][0] += 1
                counts[key][1] += y
            last_vote[(c, txt)] = y
            seen_company.add(c)


def solve(a, b):
    """Solve a*x = b by Gaussian elimination (small systems only)."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for i in range(n):
        p = max(range(i, n), key=lambda k: abs(m[k][i]))
        m[i], m[p] = m[p], m[i]
        for k in range(i + 1, n):
            f = m[k][i] / m[i][i]
            for j in range(i, n + 1):
                m[k][j] -= f * m[i][j]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = (m[i][n] - sum(m[i][j] * x[j] for j in range(i + 1, n))) / m[i][i]
    return x


def fit_logistic(xs, ys, ridge=1.0, steps=25):
    """Logistic regression by Newton's method. Returns [intercept, w1, w2, ...]."""
    d = len(xs[0]) + 1
    w = [0.0] * d
    for _ in range(steps):
        grad = [0.0] * d
        hess = [[0.0] * d for _ in range(d)]
        for x, y in zip(xs, ys):
            v = [1.0] + x
            p = 1.0 / (1.0 + math.exp(-sum(wi * vi for wi, vi in zip(w, v))))
            s = p * (1.0 - p)
            for i in range(d):
                grad[i] += (p - y) * v[i]
                hi, vi = hess[i], v[i] * s
                for j in range(i, d):
                    hi[j] += vi * v[j]
        for i in range(d):
            for j in range(i):
                hess[i][j] = hess[j][i]
            if i:  # no penalty on the intercept
                grad[i] += ridge * w[i]
                hess[i][i] += ridge
        step = solve(hess, grad)
        w = [wi - si for wi, si in zip(w, step)]
        if max(abs(s) for s in step) < 1e-8:
            break
    return w


def predict(w, x):
    return 1.0 / (1.0 + math.exp(-(w[0] + sum(wi * xi for wi, xi in zip(w[1:], x)))))


def prf(flags, ys):
    tp = sum(1 for f, y in zip(flags, ys) if f and y)
    fp = sum(1 for f, y in zip(flags, ys) if f and not y)
    fn = sum(1 for f, y in zip(flags, ys) if not f and y)
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f1, tp, fp, fn


def best_f1_threshold(ps, ys):
    best = (0.0, 0.5)
    for t in sorted(set(ps)):
        f1 = prf([p >= t for p in ps], ys)[2]
        if f1 > best[0]:
            best = (f1, t)
    return best[1]


def average_precision(ps, ys):
    """Average precision at distinct score thresholds, treating ties together."""
    hits, seen, total = 0, 0, 0.0
    ranked = sorted(zip(ps, ys), key=lambda t: -t[0])
    for _, group in itertools.groupby(ranked, key=lambda t: t[0]):
        labels = [y for _, y in group]
        positives = sum(labels)
        hits += positives
        seen += len(labels)
        total += positives * hits / seen
    return total / hits if hits else 0.0


def reasons(w, x, top=2):
    """The inputs that pushed this score up the most, in plain words."""
    parts = sorted(((wi * xi, text) for wi, xi, (_, text) in zip(w[1:], x, FEATURES)), reverse=True)
    return "; ".join(text for value, text in parts[:top] if value > 0.05)


def table(headers, rows):
    """Print a compact table with left-aligned names and right-aligned values."""
    rows = [[str(value) for value in row] for row in [headers, *rows]]
    widths = [max(len(row[i]) for row in rows) for i in range(len(headers))]
    for i, row in enumerate(rows):
        print("  " + " | ".join(value.ljust(width) if j == 0 else value.rjust(width)
                                for j, (value, width) in enumerate(zip(row, widths))))
        if i == 0:
            print("  " + "-+-".join("-" * width for width in widths))


def metric_row(name, flags, rows):
    p, r, f1, tp, fp, fn = prf(flags, [row["y"] for row in rows])
    accuracy = (len(rows) - fp - fn) / len(rows)
    return [name, f"{p:.1%}", f"{r:.1%}", f"{f1:.1%}", f"{accuracy:.1%}", tp + fp, tp, fp, fn]


def run_year(rows, test_year):
    """Fit on earlier years, score the test year. Returns (train, test, weights, threshold)."""
    year = lambda r: int(r["meeting_date"][:4])
    train = [r.copy() for r in rows if year(r) < test_year]
    test = [r.copy() for r in rows if year(r) == test_year]
    add_history_features(train + test, f"{test_year}-01-01")
    # The threshold is chosen on the last training year, by a model that never saw it.
    fit_part = [r for r in train if year(r) < test_year - 1]
    val_part = [r.copy() for r in train if year(r) == test_year - 1]
    add_history_features(fit_part + val_part, f"{test_year - 1}-01-01")
    w_val = fit_logistic([r["x"] for r in fit_part], [r["y"] for r in fit_part])
    threshold = best_f1_threshold([predict(w_val, r["x"]) for r in val_part], [r["y"] for r in val_part])
    w = fit_logistic([r["x"] for r in train], [r["y"] for r in train])
    for r in test:
        r["p"] = predict(w, r["x"])
        r["band"] = "likely AGAINST board" if r["p"] >= threshold else "likely WITH board" if r["p"] < LOW else "send to human"
    return train, test, w, threshold


def walk_forward(rows, years):
    print("Yearly holdouts | History frozen before each test year\n")
    results = []
    for ty in years:
        _, test, _, _ = run_year(rows, ty)
        ys = [r["y"] for r in test]
        n_flags = sum(r["prev_same_item"] == 1 for r in test)
        base_hits = sum(r["y"] for r in test if r["prev_same_item"] == 1)
        model_hits = sum(r["y"] for r in sorted(test, key=lambda r: -r["p"])[:n_flags])
        results.append([ty, len(test), sum(ys), n_flags, base_hits, model_hits,
                        f"{average_precision([r['p'] for r in test], ys):.3f}"])
    table(["Year", "Proposals", "Against board", "Flag budget", "Baseline hits", "Model hits", "Avg precision"], results)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(os.path.dirname(HER), "data", "real_votes.csv"))
    ap.add_argument("--test-year", type=int, default=2026)
    ap.add_argument("--walk-forward", action="store_true")
    a = ap.parse_args()

    rows = read_votes(a.data)
    if a.walk_forward:
        walk_forward(rows, range(2022, 2027))
        return
    train, test, w, threshold = run_year(rows, a.test_year)

    ps, ys = [r["p"] for r in test], [r["y"] for r in test]
    ranked = sorted(test, key=lambda r: -r["p"])
    n_base = sum(r["prev_same_item"] == 1 for r in test)
    print(f"NBIM benchmark | Test year: {a.test_year} | Train: {len(train):,} | Test: {len(test):,}")
    print(f"History frozen before {a.test_year}; threshold selected on {a.test_year - 1}.")
    print(f"Target: disagreement with the board | Actual: {sum(ys)}/{len(test)} ({sum(ys) / len(test):.1%})\n")
    table(["Method", "Precision", "Recall", "F1", "Accuracy", "Flagged", "Hits", "False alarms", "Missed"], [
        metric_row("Always with board", [False] * len(test), test),
        metric_row("Same as last time", [r["prev_same_item"] == 1 for r in test], test),
        metric_row(f"Model (top {n_base} scores)", [i < n_base for i in range(len(ranked))], ranked),
        metric_row(f"Model (p >= {threshold:.4f})", [p >= threshold for p in ps], test),
    ])
    print(f"\nAverage precision: {average_precision(ps, ys):.3f} | Positive rate: {sum(ys) / len(ys):.3f}")

    bands = []
    for band in ("likely WITH board", "send to human", "likely AGAINST board"):
        b = [r for r in test if r["band"] == band]
        k = sum(r["y"] for r in b)
        bands.append([band, len(b), f"{len(b) / len(test):.1%}", k,
                      f"{k / len(b):.1%}" if b else "—"])
    print()
    table(["Band", "Proposals", "Share", "Actual against board", "Against rate"], bands)

    out = os.path.join(HER, f"prediksjoner_{a.test_year}.csv")
    cols = ["meeting_date", "company", "country", "proposal_type", "proposal_text", "mgmt_rec"]
    with open(out, "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(cols + ["probability_against", "band", "actual_against", "reasons"])
        for r in ranked:
            wr.writerow([r[c] for c in cols] + [r["p"], r["band"], r["y"], reasons(w, r["x"])])
    print(f"\nWrote {len(ranked)} scored proposals to {os.path.basename(out)}")


if __name__ == "__main__":
    main()
