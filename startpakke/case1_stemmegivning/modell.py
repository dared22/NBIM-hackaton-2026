"""Scoring model for NBIM votes: will NBIM vote against the board?

Run:
    python3 modell.py                 # trains on years before 2026, tests on 2026
    python3 modell.py --test-year 2025
    python3 modell.py --walk-forward  # same test repeated for 2022-2026

Data: real_votes.csv (NBIM's published votes, handed out by the organisers).
Only the Python standard library is used, so the result is reproducible anywhere.

What it does
    1. Cleans the data and drops rows without a board recommendation to compare to.
    2. Builds features that only use votes from EARLIER meeting dates.
    3. Measures two baselines: "always with the board" and "same as last time".
    4. Fits a logistic regression on the training years and scores the test year.
    5. Sorts every proposal into a band: likely FOR, send to a human, or
       likely AGAINST.
    6. Writes one row per test proposal to prediksjoner_<year>.csv, with the
       probability, the band and the reasons behind it.

Columns never used as inputs, because they contain the answer: nbim_vote,
nbim_vote_raw, against_board, rationale_text, position_paper, rationale_section.
"""

import argparse
import collections
import csv
import math
import os
import random
import re

HER = os.path.dirname(os.path.abspath(__file__))

# Smoothing strength: how many "virtual" votes the broader average counts for.
M = 8.0
# History inputs are capped at +/- CLIP so one company with an extreme record
# (hundreds of items in one year) cannot dominate. Chosen on test years 2022-2025.
CLIP = 1.0
# Below LOW the proposal goes in the "likely FOR" band. 5% is NBIM's overall
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


def add_history_features(rows):
    """Attach features computed only from meetings on earlier dates.

    All rows from one date are scored before any of them are added to the
    history, so a meeting can never see its own outcome.
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
    for t in sorted(set(round(p, 3) for p in ps)):
        f1 = prf([p >= t for p in ps], ys)[2]
        if f1 > best[0]:
            best = (f1, t)
    return best[1]


def average_precision(ps, ys):
    hits, total = 0, 0.0
    for i, (_, y) in enumerate(sorted(zip(ps, ys), key=lambda t: -t[0]), 1):
        if y:
            hits += 1
            total += hits / i
    return total / hits if hits else 0.0


def bootstrap(rows, flags, n=1000, seed=1):
    """95% interval for precision and recall, resampling whole companies."""
    groups = collections.defaultdict(list)
    for r, f in zip(rows, flags):
        groups[r["company_id"]].append((f, r["y"]))
    keys = sorted(groups)
    rng = random.Random(seed)
    ps, rs = [], []
    for _ in range(n):
        sample = [fy for k in rng.choices(keys, k=len(keys)) for fy in groups[k]]
        p, r = prf([f for f, _ in sample], [y for _, y in sample])[:2]
        ps.append(p)
        rs.append(r)
    ps.sort()
    rs.sort()
    lo, hi = int(0.025 * n), int(0.975 * n) - 1
    return (ps[lo], ps[hi]), (rs[lo], rs[hi])


def reasons(w, x, top=2):
    """The inputs that pushed this score up the most, in plain words."""
    parts = sorted(((wi * xi, text) for wi, xi, (_, text) in zip(w[1:], x, FEATURES)), reverse=True)
    return "; ".join(text for value, text in parts[:top] if value > 0.05)


def line(name, flags, rows):
    ys = [r["y"] for r in rows]
    p, r, f1, tp, fp, fn = prf(flags, ys)
    (plo, phi), (rlo, rhi) = bootstrap(rows, flags)
    print(f"  {name:<34} precision {p:5.1%} [{plo:.0%}-{phi:.0%}]   recall {r:5.1%} [{rlo:.0%}-{rhi:.0%}]"
          f"   F1 {f1:5.1%}   flagged {tp + fp:4d}   hits {tp:3d}   missed {fn:3d}")


def run_year(rows, test_year):
    """Fit on earlier years, score the test year. Returns (test rows, weights, threshold)."""
    year = lambda r: int(r["meeting_date"][:4])
    train = [r for r in rows if year(r) < test_year]
    test = [r for r in rows if year(r) == test_year]
    # The threshold is chosen on the last training year, by a model that never saw it.
    fit_part = [r for r in train if year(r) < test_year - 1]
    val_part = [r for r in train if year(r) == test_year - 1]
    w_val = fit_logistic([r["x"] for r in fit_part], [r["y"] for r in fit_part])
    threshold = best_f1_threshold([predict(w_val, r["x"]) for r in val_part], [r["y"] for r in val_part])
    w = fit_logistic([r["x"] for r in train], [r["y"] for r in train])
    for r in test:
        r["p"] = predict(w, r["x"])
        r["band"] = "likely FOR" if r["p"] < LOW else "likely AGAINST" if r["p"] >= threshold else "send to human"
    return train, test, w, threshold


def walk_forward(rows, years):
    print("Same test repeated: train on all earlier years, test on the year shown\n")
    print(f"  {'year':<7}{'against':>8}{'baseline hits':>15}{'model hits':>12}{'flags':>7}"
          f"{'likely FOR':>13}{'hidden there':>14}{'avg precision':>15}")
    tot = collections.Counter()
    for ty in years:
        _, test, _, _ = run_year(rows, ty)
        ys = [r["y"] for r in test]
        n_flags = sum(1 for r in test if r["prev_same_item"] == 1)
        base_hits = sum(r["y"] for r in test if r["prev_same_item"] == 1)
        model_hits = sum(r["y"] for r in sorted(test, key=lambda r: -r["p"])[:n_flags])
        low = [r for r in test if r["band"] == "likely FOR"]
        tot.update(n=len(test), pos=sum(ys), flags=n_flags, base=base_hits, model=model_hits,
                   low=len(low), low_pos=sum(r["y"] for r in low))
        print(f"  {ty:<7}{sum(ys):>8}{base_hits:>15}{model_hits:>12}{n_flags:>7}"
              f"{len(low) / len(test):>13.0%}{sum(r['y'] for r in low) / sum(ys):>14.0%}"
              f"{average_precision([r['p'] for r in test], ys):>15.2f}")
    print(f"  {'all':<7}{tot['pos']:>8}{tot['base']:>15}{tot['model']:>12}{tot['flags']:>7}"
          f"{tot['low'] / tot['n']:>13.0%}{tot['low_pos'] / tot['pos']:>14.0%}")
    print("\n  baseline hits / model hits: real against-votes found when both may flag the same")
    print("  number of proposals ('flags' = how many the same-as-last-time baseline flags).")
    print("  likely FOR: share of proposals the model would wave through; hidden there: share")
    print("  of all against-votes that sit in that band and would be missed.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(HER, "real_votes.csv"))
    ap.add_argument("--test-year", type=int, default=2026)
    ap.add_argument("--walk-forward", action="store_true")
    a = ap.parse_args()

    rows = read_votes(a.data)
    add_history_features(rows)
    if a.walk_forward:
        walk_forward(rows, range(2022, 2027))
        return
    train, test, w, threshold = run_year(rows, a.test_year)

    print(f"Data: {len(rows)} proposals with a known board recommendation")
    print(f"Train: {len(train)} proposals before {a.test_year}, {sum(r['y'] for r in train)} against the board")
    print(f"Test:  {len(test)} proposals in {a.test_year}, {sum(r['y'] for r in test)} against the board "
          f"({sum(r['y'] for r in test) / len(test):.1%})\n")

    ps, ys = [r["p"] for r in test], [r["y"] for r in test]
    ranked = sorted(test, key=lambda r: -r["p"])

    print(f"Results on {a.test_year} (95% interval in brackets, resampling companies)")
    line("Baseline: always with the board", [False] * len(test), test)
    line("Baseline: same as last time", [r["prev_same_item"] == 1 for r in test], test)
    n_base = sum(1 for r in test if r["prev_same_item"] == 1)
    cut = ranked[n_base - 1]["p"] if n_base else 2.0
    line(f"Model, same number of flags", [p >= cut for p in ps], test)
    line(f"Model, threshold {threshold:.2f}", [p >= threshold for p in ps], test)
    print(f"\n  Average precision: model {average_precision(ps, ys):.3f}, "
          f"random {sum(ys) / len(ys):.3f}")

    print("\nBands: what a human would have to read")
    for band in ("likely FOR", "send to human", "likely AGAINST"):
        b = [r for r in test if r["band"] == band]
        k = sum(r["y"] for r in b)
        print(f"  {band:<15} {len(b):4d} proposals ({len(b) / len(test):4.0%})   {k:3d} real against-votes "
              f"({k / sum(ys):4.0%} of all)   against-rate in band {k / len(b) if b else 0:5.1%}")

    print("\nRanked list: how many real against-votes are in the model's top N")
    for k in (25, 50, 100, 200):
        hits = sum(r["y"] for r in ranked[:k])
        print(f"  top {k:3d}: {hits:3d} hits   precision {hits / k:5.1%}   recall {hits / sum(ys):5.1%}")

    print("\nIs the confidence honest? (predicted vs actual share against)")
    for lo, hi in ((0, .02), (.02, .05), (.05, .15), (.15, .35), (.35, .6), (.6, 1.01)):
        b = [r for r in test if lo <= r["p"] < hi]
        if b:
            print(f"  predicted {lo:4.0%}-{min(hi, 1):4.0%}: {len(b):4d} proposals   "
                  f"model says {sum(r['p'] for r in b) / len(b):5.1%}   actual {sum(r['y'] for r in b) / len(b):5.1%}")

    print("\nBy proposal type (types with at least 3 against-votes in the test year)")
    types = collections.defaultdict(list)
    for r in test:
        types[r["proposal_type"]].append(r)
    for t, rs in sorted(types.items(), key=lambda kv: -sum(r["y"] for r in kv[1])):
        if sum(r["y"] for r in rs) >= 3:
            p, rec, _, tp, fp, fn = prf([r["p"] >= threshold for r in rs], [r["y"] for r in rs])
            print(f"  {t:<20} {len(rs):4d} proposals   {tp + fn:3d} against   precision {p:5.1%}   recall {rec:5.1%}")

    print("\nModel weights (positive = pushes towards AGAINST)")
    for (name, text), wi in zip(FEATURES, w[1:]):
        print(f"  {wi:+6.2f}  {name:<18} {text}")

    out = os.path.join(HER, f"prediksjoner_{a.test_year}.csv")
    cols = ["meeting_date", "company", "country", "proposal_type", "proposal_text", "mgmt_rec"]
    with open(out, "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(cols + ["probability_against", "band", "actual_against", "reasons"])
        for r in ranked:
            wr.writerow([r[c] for c in cols] + [f"{r['p']:.3f}", r["band"], r["y"], reasons(w, r["x"])])
    print(f"\nWrote {len(ranked)} scored proposals to {os.path.basename(out)}")


if __name__ == "__main__":
    main()
