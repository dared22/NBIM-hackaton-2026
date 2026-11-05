"""Pay-vote model: will NBIM vote against the board on executive pay?

Run from the repo root (no internet, no API key):
    python3 agent/pay_model.py

This is the "company facts" test. The history model and the rule check could
not find against-votes on items NBIM had not opposed before, because the
proposal wording does not contain the reason. Here the model also gets one
company fact per vote: the CEO's total pay, as filed with the SEC before the
meeting.

Data
    data/nbim_pay_votes.csv    NBIM's say-on-pay votes, from Norges Bank's own
                               SEC Form N-PX filings (CIK 1374170), 3 seasons
    data/ceo_pay.csv           CEO pay facts with filing dates (fetch_ceo_pay.py)
    data/pay_company_link.csv  which company name was linked to which SEC number

Seasons run July to June. Train on seasons 2024 and 2025, test on season 2026.

Which pay figure counts as known before a meeting
    A proxy statement for an annual meeting must report pay for the last
    completed fiscal year, and it is filed before the meeting. So for each vote
    the model uses the pay figure for the latest fiscal year that ended at
    least 60 days before the meeting date.

Limits of the pay data, to be stated with any result
    - The SEC API only exposes each company's newest filing (all from 2026).
      Earlier years come from the five-year table in that filing, so the value
      is the one reported in 2026, not a copy of the original filing. No
      fiscal year in the data has more than one reported value.
    - Companies that stopped filing before 2026 (merged, delisted) have no
      figure. The model has no "figure exists" input, so that gap cannot be
      used as a signal.
    - Only about a third of the companies have a CEO figure in this API; a
      further sixth have only the other executives' average.

Why 25 million dollars: NBIM's own voting review (first half 2025) says it
applies a stricter assessment to US packages worth 25 million dollars or more.
The level comes from that publication. It was not tuned on these votes.
"""

import collections
import csv
import datetime
import math
import os
import random
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from benchmark import model as bm  # noqa: E402

VOTES = os.path.join(ROOT, "data", "nbim_pay_votes.csv")
PAY = os.path.join(ROOT, "data", "ceo_pay.csv")
LINK = os.path.join(ROOT, "data", "pay_company_link.csv")
TEST_SEASON = 2026
STRICT_LEVEL = 25e6
LOW = 0.05

FEATURES = [
    ("prev_against", "NBIM voted against this company's pay last season", "GVG 3.3.5"),
    ("prev_for", "NBIM supported this company's pay last season", ""),
    ("pay_size", "size of the CEO's total pay", "GVG 3.3.8"),
    ("pay_25m", "CEO pay is at or above the 25 million dollar level NBIM reviews more strictly", "GVG 3.3.8"),
    ("pay_doubled", "CEO pay at least doubled from the year before", "GVG 3.3.6"),
    ("ceo_vs_others", "CEO pay is many times the other executives' average", "GVG 3.3.3"),
    ("others_size", "size of the other named executives' average pay", "GVG 3.3.8"),
]
HISTORY_ONLY = [0, 1]


def read_votes():
    """Annual say-on-pay votes, one row per vote, with season and target."""
    seen, rows, other = set(), [], collections.Counter()
    with open(VOTES, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            key = tuple(r.values())
            if key in seen:
                continue
            seen.add(key)
            text = r["forslag"].lower()
            if r["stemme"] not in ("FOR", "AGAINST", "WITHHOLD"):
                other["no for/against vote (frequency votes, blanks)"] += 1
            elif "frequency" in text:
                other["frequency of the pay vote"] += 1
            elif re.search(r"merger|golden parachute|transaction|in connection with|business combination|arrangement", text):
                other["merger payouts"] += 1
                other["merger payouts against"] += r["for_eller_mot_ledelsen"] == "AGAINST"
            else:
                r["y"] = 1 if r["for_eller_mot_ledelsen"] == "AGAINST" else 0
                r["season"] = int(r["innsendt"][:4])
                rows.append(r)
    rows.sort(key=lambda r: (r["moetedato"], r["cusip"], r["forslag"]))
    return rows, other


def load_pay():
    link = {}
    with open(LINK, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r["status"] == "linked":
                link[r["cusip"]] = int(r["cik"])
    facts = collections.defaultdict(lambda: collections.defaultdict(list))
    with open(PAY, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            facts[int(r["cik"])][r["tag"]].append(r)
    return link, facts


def minus_days(date, days):
    return (datetime.date.fromisoformat(date) - datetime.timedelta(days=days)).isoformat()


def latest_before(facts, date, skip=0):
    """Newest fiscal year that ended at least 60 days before `date`, but not more
    than two years before. skip=1 gives the fiscal year before that one."""
    known = {}
    for f in facts:
        if f["period_end"] <= minus_days(date, 60):
            best = known.get(f["period_end"])
            if best is None or f["filed"] > best["filed"]:
                known[f["period_end"]] = f
    ends = sorted(known, reverse=True)
    if not ends or ends[0] < minus_days(date, 730):
        return None
    return known[ends[skip]] if len(ends) > skip else None


def add_features(rows, link, facts):
    prev = {(r["season"], r["cusip"]): r["y"] for r in rows}
    for r in rows:
        last = prev.get((r["season"] - 1, r["cusip"]))
        cik = link.get(r["cusip"])
        fact = latest_before(facts[cik]["PeoTotalCompAmt"], r["moetedato"]) if cik else None
        pay = float(fact["value_usd"]) if fact else None
        before = latest_before(facts[cik]["PeoTotalCompAmt"], r["moetedato"], 1) if fact else None
        other_fact = latest_before(facts[cik]["NonPeoNeoAvgTotalCompAmt"], r["moetedato"]) if cik else None
        others = float(other_fact["value_usd"]) if other_fact and float(other_fact["value_usd"]) > 0 else None
        ok = pay is not None and pay > 0
        r["pay"], r["pay_fact"], r["prev"] = (pay if ok else None), (fact if ok else None), last
        r["pay_before"] = float(before["value_usd"]) if ok and before else None
        r["others"], r["others_fact"] = others, (other_fact if others else None)
        same_year = ok and others and other_fact["period_end"] == fact["period_end"]
        ratio = pay / others if same_year else None
        # A missing figure gives 0 on every pay input, the same as an average-sized package.
        r["x"] = [
            1.0 if last == 1 else 0.0,
            1.0 if last == 0 else 0.0,
            max(-1.0, min(1.5, math.log10(pay / 1e7))) if ok else 0.0,
            1.0 if ok and pay >= STRICT_LEVEL else 0.0,
            1.0 if ok and r["pay_before"] and r["pay_before"] > 0 and pay / r["pay_before"] >= 2 else 0.0,
            max(-1.0, min(2.0, math.log2(ratio / 3))) if ratio else 0.0,
            max(-1.0, min(1.5, math.log10(others / 3e6))) if others else 0.0,
        ]


def fit_predict(train, test, cols):
    w = bm.fit_logistic([[r["x"][i] for i in cols] for r in train], [r["y"] for r in train])
    return w, [bm.predict(w, [r["x"][i] for i in cols]) for r in test]


def top_flags(ps, n):
    """Flag the n highest scores (ties broken by position, so the count is exact)."""
    order = sorted(range(len(ps)), key=lambda i: -ps[i])[:n]
    flags = [False] * len(ps)
    for i in order:
        flags[i] = True
    return flags


def interval(flags, ys, n=1000, seed=3):
    """95% interval for precision and recall, resampling votes."""
    rng, ps, rs = random.Random(seed), [], []
    idx = list(range(len(ys)))
    for _ in range(n):
        s = rng.choices(idx, k=len(idx))
        p, r = bm.prf([flags[i] for i in s], [ys[i] for i in s])[:2]
        ps.append(p)
        rs.append(r)
    ps.sort()
    rs.sort()
    return f"{ps[25]:.0%}-{ps[974]:.0%}", f"{rs[25]:.0%}-{rs[974]:.0%}"


def metric(name, flags, ys):
    p, r, f1, tp, fp, fn = bm.prf(flags, ys)
    pi, ri = interval(flags, ys)
    return [name, f"{p:.1%}", pi, f"{r:.1%}", ri, f"{f1:.1%}", tp + fp, tp, fp, fn]


def money(v):
    return f"${v / 1e6:.1f}m"


def reasons(r, w):
    """Plain-language reasons for the score, with the source of each pay figure."""
    out = []
    parts = sorted(((wi * xi, i) for i, (wi, xi) in enumerate(zip(w[1:], r["x"]))), reverse=True)
    for value, i in parts:
        if value <= 0.05:
            continue
        name, text, rule = FEATURES[i]
        if name in ("pay_size", "pay_25m") and r["pay_fact"]:
            f = r["pay_fact"]
            text = (f"CEO total pay {money(r['pay'])} for the year to {f['period_end']}"
                    + (" is at or above the 25 million dollar level NBIM reviews more strictly"
                       if r["pay"] >= STRICT_LEVEL else "")
                    + f" (source: {f['form']} filed {f['filed']}, SEC accession {f['accession']})")
        elif name == "pay_doubled":
            text = f"CEO pay rose from {money(r['pay_before'])} to {money(r['pay'])}"
        elif name == "ceo_vs_others":
            text = f"CEO pay is {r['pay'] / r['others']:.1f} times the other executives' average ({money(r['others'])})"
        elif name == "others_size":
            f = r["others_fact"]
            text = (f"the other named executives averaged {money(r['others'])} for the year to {f['period_end']}"
                    f" (source: {f['form']} filed {f['filed']}, SEC accession {f['accession']})")
        if text not in [t for t, _ in out]:
            out.append((text, rule))
    return out[:3]


def main():
    rows, other = read_votes()
    link, facts = load_pay()
    add_features(rows, link, facts)

    train = [r for r in rows if r["season"] < TEST_SEASON]
    test = [r for r in rows if r["season"] == TEST_SEASON]
    ys = [r["y"] for r in test]
    cols = list(range(len(FEATURES)))

    print(f"NBIM say-on-pay votes: {len(rows)} annual pay votes at {len({r['cusip'] for r in rows})} companies")
    print(f"Left out: {other['frequency of the pay vote'] + other['no for/against vote (frequency votes, blanks)']} "
          f"frequency votes and blanks (NBIM never opposed the board on these), and {other['merger payouts']} "
          f"merger payout votes ({other['merger payouts against']} against, one-off events with no history)")
    print(f"Train: seasons before {TEST_SEASON}, {len(train)} votes, {sum(r['y'] for r in train)} against the board")
    print(f"Test:  season {TEST_SEASON}, {len(test)} votes, {sum(ys)} against the board ({sum(ys) / len(ys):.1%})")
    cover = sum(1 for r in test if r["pay"])
    either = sum(1 for r in test if r["pay"] or r["others"])
    print(f"Pay figure for the last fiscal year before the meeting: CEO pay for {cover} of {len(test)} test votes "
          f"({cover / len(test):.0%}); CEO or other executives' pay for {either} ({either / len(test):.0%})\n")

    w, ps = fit_predict(train, test, cols)
    w_hist, ps_hist = fit_predict(train, test, HISTORY_ONLY)
    base = [r["prev"] == 1 for r in test]
    n = sum(base)
    # The cut-off is chosen on the training seasons, never on the test season.
    _, ps_train = fit_predict(train, train, cols)
    thr = bm.best_f1_threshold(ps_train, [r["y"] for r in train])

    print(f"Results on season {TEST_SEASON} (95% intervals from resampling votes)")
    bm.table(["Method", "Precision", "95%", "Recall", "95%", "F1", "Flagged", "Hits", "False alarms", "Missed"],
             [metric("Always with board", [False] * len(test), ys),
              metric("Same as last season", base, ys),
              metric(f"History only, top {n}", top_flags(ps_hist, n), ys),
              metric(f"History + CEO pay, top {n}", top_flags(ps, n), ys),
              metric(f"History + CEO pay, p >= {thr:.2f}", [p >= thr for p in ps], ys)])
    print(f"\n  'top {n}' rows flag exactly as many votes as the same-as-last-season baseline, so they compare like for like.")
    print(f"  Average precision: history + CEO pay {bm.average_precision(ps, ys):.3f}, "
          f"history only {bm.average_precision(ps_hist, ys):.3f}, random {sum(ys) / len(ys):.3f}")
    rate = sum(r["y"] for r in train) / len(train)
    print(f"  Brier score (lower is better): model {sum((p - y) ** 2 for p, y in zip(ps, ys)) / len(ys):.4f}, "
          f"always saying {rate:.1%} {sum((rate - y) ** 2 for y in ys) / len(ys):.4f}")

    print("\nOnly the test votes with a pay figure (CEO or other executives)")
    sub = [i for i, r in enumerate(test) if r["pay"] or r["others"]]
    sy = [ys[i] for i in sub]
    k = sum(base[i] for i in sub)
    bm.table(["Method", "Precision", "95%", "Recall", "95%", "F1", "Flagged", "Hits", "False alarms", "Missed"],
             [metric("Same as last season", [base[i] for i in sub], sy),
              metric(f"History + CEO pay, top {k}", top_flags([ps[i] for i in sub], k), sy)])

    print("\nNew situations: against-votes at companies NBIM did not oppose last season")
    new = [i for i, r in enumerate(test) if r["y"] and r["prev"] != 1]
    flagged = top_flags(ps, n)
    print(f"  {len(new)} such votes. Same-as-last-season finds 0 by construction; "
          f"history + CEO pay finds {sum(flagged[i] for i in new)} in its top {n} "
          f"and {sum(1 for i in new if ps[i] >= thr)} at p >= {thr:.2f}.")

    print("\nBands on the test season")
    out = []
    for name, keep in (("likely WITH board", lambda p: p < LOW), ("send to human", lambda p: LOW <= p < thr),
                       ("likely AGAINST board", lambda p: p >= thr)):
        b = [y for p, y in zip(ps, ys) if keep(p)]
        out.append([name, len(b), f"{len(b) / len(ys):.0%}", sum(b), f"{sum(b) / sum(ys):.0%}",
                    f"{sum(b) / len(b):.1%}" if b else "-"])
    bm.table(["Band", "Votes", "Share", "Real against-votes", "Share of all against", "Against rate"], out)

    print("\nIs the confidence honest? (predicted vs actual share against)")
    out = []
    for lo, hi in ((0, .05), (.05, .15), (.15, .35), (.35, .6), (.6, 1.01)):
        b = [(p, y) for p, y in zip(ps, ys) if lo <= p < hi]
        if b:
            out.append([f"{lo:.0%}-{min(hi, 1):.0%}", len(b), f"{sum(p for p, _ in b) / len(b):.1%}",
                        f"{sum(y for _, y in b) / len(b):.1%}"])
    bm.table(["Predicted", "Votes", "Model says", "Actual"], out)

    print("\nAgainst rate by CEO pay, test season (the fact the wording does not contain)")
    out = []
    for name, lo, hi in (("under $10m", 0, 10e6), ("$10-25m", 10e6, 25e6), ("$25-40m", 25e6, 40e6), ("$40m or more", 40e6, 1e15)):
        b = [r["y"] for r in test if r["pay"] and lo <= r["pay"] < hi]
        out.append([name, len(b), sum(b), f"{sum(b) / len(b):.0%}" if b else "-"])
    b = [r["y"] for r in test if not r["pay"]]
    out.append(["no CEO figure", len(b), sum(b), f"{sum(b) / len(b):.0%}"])
    bm.table(["CEO total pay", "Votes", "Against", "Against rate"], out)

    print("\nModel weights (positive = pushes towards AGAINST)")
    for (name, text, _), wi in zip(FEATURES, w[1:]):
        print(f"  {wi:+6.2f}  {name:<14} {text}")

    path = os.path.join(ROOT, "agent", f"pay_votes_{TEST_SEASON}.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["meeting_date", "company", "proposal", "probability_against", "band", "ceo_pay_usd",
                     "pay_source", "reasons", "guideline_rules", "actual_against"])
        for r, p in sorted(zip(test, ps), key=lambda t: -t[1]):
            why = reasons(r, w)
            src = r["pay_fact"]
            wr.writerow([r["moetedato"], r["utsteder"], r["forslag"], f"{p:.3f}",
                         "likely AGAINST board" if p >= thr else "likely WITH board" if p < LOW else "send to human",
                         f"{r['pay']:.0f}" if r["pay"] else "",
                         f"fiscal year to {src['period_end']}, {src['form']} filed {src['filed']}, accession {src['accession']}" if src else "",
                         " | ".join(t for t, _ in why), ", ".join(sorted({c for _, c in why if c})), r["y"]])
    print(f"\nWrote {len(test)} scored votes to {os.path.relpath(path, ROOT)}")


if __name__ == "__main__":
    main()
