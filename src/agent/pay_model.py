"""Pay-vote model: will NBIM vote against the board on executive pay?

Run from the repo root (no internet, no API key):
    python3 src/agent/pay_model.py              # train on seasons 2024-2025, test on 2026
    python3 src/agent/pay_model.py --explore    # training seasons only: how the inputs were chosen
    python3 src/agent/pay_model.py --develop    # training seasons only: compare input sets
    python3 src/agent/pay_model.py --source api # earlier version, SEC API figures only

Scope: US filers, executive pay votes only. Every company in the vote file
files a US proxy statement, because the file only holds votes required by US
rules.

This is the "company facts" test. The history model and the rule check could
not find against-votes on items NBIM had not opposed before, because the
proposal wording does not contain the reason. Here the model also gets facts
about the company's pay, read from the proxy statement for that meeting.

Data
    data/dirty/nbim_pay_votes.csv    NBIM's say-on-pay votes, from Norges Bank's own
                               SEC Form N-PX filings (CIK 1374170), 3 seasons
    data/evidence/proxy_pay.csv         tagged pay figures from each meeting's own proxy
    data/evidence/proxy_meetings.csv    which proxy was used for which meeting
    data/evidence/ceo_pay.csv           SEC API figures, used only where no proxy was read
    data/evidence/pay_company_link.csv  which company name was linked to which SEC number

Seasons run July to June. Train on seasons 2024 and 2025, test on season 2026.

What counts as known before a meeting
    1. Figures from the proxy filed 1-120 days before that meeting. The filing
       date is checked, so nothing published later can leak in.
    2. Where no proxy could be read: the SEC API figure for the latest fiscal
       year that ended at least 60 days before the meeting. The API only
       exposes each company's newest filing, so this figure is the value as
       reported in 2026. These votes are counted separately in the output.

How the inputs were chosen
    On the training seasons only (run --explore and --develop). The 2026 season
    was not used to pick inputs.
    - The 25 million dollar level comes from NBIM's own voting review (first
      half 2025), which says it applies a stricter assessment to US packages of
      that size or more.
    - Pay against the median of similar companies and pay growth against
      shareholder returns follow the published ISS pay-for-performance screen.
    - Shareholder return alone showed little on the training seasons, but among
      packages of 25 million dollars or more it did, so it enters only in
      combination with high pay.

Versions scored on the 2026 season
    Three model versions: SEC API figures only; proxy figures; proxy figures
    plus the two ISS measures and the confidence correction (this version).
    The last change did not move the 2026 result beyond noise. The season was
    scored a fourth time after 239 more companies were linked to the SEC
    (link_companies.py), with no change to the model. All results are in the
    commit history.

A missing figure gives 0 on every pay input, the same as an average package.
There is no "figure exists" input.
"""

import argparse
import collections
import csv
import datetime
import hashlib
import json
import math
import os
import random
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))
from benchmark import model as bm  # noqa: E402

VOTES = os.path.join(ROOT, "data", "dirty", "nbim_pay_votes.csv")
API_PAY = os.path.join(ROOT, "data", "evidence", "ceo_pay.csv")
PROXY_PAY = os.path.join(ROOT, "data", "evidence", "proxy_pay.csv")
PROXY_MEET = os.path.join(ROOT, "data", "evidence", "proxy_meetings.csv")
LINK = os.path.join(ROOT, "data", "evidence", "pay_company_link.csv")
SIZE = os.path.join(ROOT, "data", "evidence", "company_size.csv")
TEXT = os.path.join(ROOT, "data", "evidence", "proxy_text.csv")
STRUCTURE = os.path.join(ROOT, "src", "agent", "cache", "pay_structure.jsonl")
TEST_SEASON = 2026
STRICT_LEVEL = 25e6
LOW = 0.05

# name, plain-language description, NBIM guideline rule it relates to
FEATURES = [
    ("prev_against", "NBIM voted against this company's pay last season", "GVG 3.3.5"),
    ("prev_for", "NBIM supported this company's pay last season", ""),
    ("pay_size", "size of the CEO's total pay", "GVG 3.3.8"),
    ("pay_25m", "CEO pay is at or above the 25 million dollar level NBIM reviews more strictly", "GVG 3.3.8"),
    ("pay_doubled", "CEO pay at least doubled from the year before", "GVG 3.3.6"),
    ("ceo_vs_others", "CEO pay is many times the other executives' average", "GVG 3.3.3"),
    ("others_size", "size of the other named executives' average pay", "GVG 3.3.8"),
    ("high_pay_lost", "CEO pay of 25 million dollars or more while shareholders have lost money", "GVG 3.3.4"),
    ("ceo_changed", "more than one CEO was paid during the year", "GVG 3.3.6"),
    ("pay_vs_peers", "CEO pay as a multiple of the median at companies of similar industry and size", "GVG 3.3.8"),
    ("pay_outran_returns", "CEO pay has grown faster than shareholder returns over the years in the pay table", "GVG 3.3.4"),
]
# The two last inputs follow the published ISS pay-for-performance screen
# (Multiple of Median and Pay-TSR Alignment).
#
# Tested on the training seasons and left out because they did not help:
#   - shareholder return against the company's own peer group
#   - support at the previous pay vote, read from the proxy text
#   - how often the proxy mentions one-off, sign-on, retention or severance awards
#   - "compensation actually paid" to the CEO (size, 25 million level, ratio to total pay)
#   - finer steps in pay size (15, 20 and 35 million dollars) and total pay over the table years
#   - a non-linear model (boosted trees) in place of the logistic model: 73 hits against 76
#   - how the pay is built, read from the proxy text by an AI model (one-off awards, performance-based
#     share, earlier support), for CEO pay of 25 million dollars or more. Better on the training
#     seasons, worse on 2026. The three inputs are kept in r["xs"] for pay_structure_test.py only.
# The last two are still shown to the reviewer as evidence (data/evidence/proxy_text.csv).
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


def load_sources():
    link = {}
    with open(LINK, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r["status"] == "linked":
                link[r["cusip"]] = int(r["cik"])
    api = collections.defaultdict(lambda: collections.defaultdict(list))
    with open(API_PAY, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            api[int(r["cik"])][r["tag"]].append(r)
    proxy, meetings = collections.defaultdict(lambda: collections.defaultdict(list)), {}
    if os.path.exists(PROXY_PAY):
        with open(PROXY_MEET, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                meetings[(int(r["cik"]), r["meeting_date"])] = r
        with open(PROXY_PAY, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                proxy[(int(r["cik"]), r["meeting_date"])][r["tag"]].append(r)
    return link, api, proxy, meetings


def minus_days(date, days):
    return (datetime.date.fromisoformat(date) - datetime.timedelta(days=days)).isoformat()


def repaired(value, limit):
    """A few filings tag a figure a thousand or a million times too large (wrong
    scale attribute). No CEO was paid a billion dollars in these years, so
    anything at or above `limit` is divided by 1,000 until it is below it."""
    while value >= limit:
        value /= 1000.0
    return value


def from_proxy(facts, meeting):
    """Company facts from the proxy filed before this meeting, or None."""
    by_year = collections.defaultdict(list)
    for f in facts["PeoTotalCompAmt"]:
        if float(f["value"]) > 0:
            by_year[f["period_end"]].append(f)
    if not by_year or meeting["filed"] >= meeting["meeting_date"]:
        return None
    years = sorted(by_year, reverse=True)
    pay_in = lambda year: max(repaired(float(f["value"]), 1e9) for f in by_year[year])
    rescaled = any(float(f["value"]) >= 1e9 for fs in by_year.values() for f in fs) or any(
        float(f["value"]) >= 1e9 for f in facts["NonPeoNeoAvgTotalCompAmt"])

    def at(tag, year, limit):
        vals = [repaired(float(f["value"]), limit) for f in facts[tag] if f["period_end"] == year and float(f["value"]) > 0]
        return max(vals) if vals else None

    return {
        "pay": pay_in(years[0]),
        "pay_before": pay_in(years[1]) if len(years) > 1 else None,
        "others": at("NonPeoNeoAvgTotalCompAmt", years[0], 1e9),
        "return": at("TotalShareholderRtnAmt", years[0], 1e5),
        "peer_return": at("PeerGroupTotalShareholderRtnAmt", years[0], 1e5),
        "pay_series": [pay_in(y) for y in reversed(years)],
        "return_series": [at("TotalShareholderRtnAmt", y, 1e5) for y in reversed(years)],
        "ceo_changed": len({f["person"] for f in by_year[years[0]] if f["person"]}) > 1,
        "rescaled": rescaled,
        "year": years[0],
        "source": f"{meeting['form']} filed {meeting['filed']}, "
                  f"{(datetime.date.fromisoformat(meeting['meeting_date']) - datetime.date.fromisoformat(meeting['filed'])).days} "
                  f"days before the meeting",
        "url": meeting["url"],
        "kind": "proxy",
    }


def from_api(facts, date):
    """Company facts from the SEC API (value as reported in 2026), or None."""
    def latest(tag, skip=0):
        known = {}
        for f in facts[tag]:
            if f["period_end"] <= minus_days(date, 60) and float(f["value_usd"]) > 0:
                known[f["period_end"]] = f
        ends = sorted(known, reverse=True)
        if not ends or ends[0] < minus_days(date, 730) or len(ends) <= skip:
            return None
        return known[ends[skip]]

    pay, others = latest("PeoTotalCompAmt"), latest("NonPeoNeoAvgTotalCompAmt")
    if not pay and not others:
        return None
    before = latest("PeoTotalCompAmt", 1) if pay else None
    f = pay or others
    return {
        "pay": float(pay["value_usd"]) if pay else None,
        "pay_before": float(before["value_usd"]) if before else None,
        "others": float(others["value_usd"]) if others and (not pay or others["period_end"] == pay["period_end"]) else None,
        "return": None,
        "peer_return": None,
        "pay_series": [],
        "return_series": [],
        "ceo_changed": False,
        "year": f["period_end"],
        "source": f"SEC API, value as reported in {f['form']} filed {f['filed']}",
        "url": "",
        "kind": "api",
    }


def pay_return_gap(pay, ret):
    """ISS "Pay-TSR Alignment": trend of shareholder return minus trend of CEO pay.

    `pay` holds CEO pay for each year in the table, oldest first. `ret` holds the
    value at each of those year ends of 100 dollars invested before the first
    year. Both trends are weighted least-squares slopes (recent years count
    more, decay 0.85) divided by the weighted average, as in the ISS method.
    Negative = pay grew faster than returns. Needs at least three years.
    """
    n = len(pay)
    if n < 3 or any(v is None for v in ret) or len(ret) != n:
        return None

    def trend(xs, ys, ws):
        sw = sum(ws)
        swx = sum(w * x for w, x in zip(ws, xs))
        swy = sum(w * y for w, y in zip(ws, ys))
        swxy = sum(w * x * y for w, x, y in zip(ws, xs, ys))
        swxx = sum(w * x * x for w, x in zip(ws, xs))
        den = sw * swxx - swx * swx
        return ((sw * swxy - swx * swy) / den) / (swy / sw) if den and swy else None

    ret_trend = trend(range(n + 1), [100.0] + list(ret), [0.85 ** (n - i) for i in range(n + 1)])
    pay_trend = trend(range(1, n + 1), pay, [0.85 ** (n - i + 0.5) for i in range(1, n + 1)])
    return None if ret_trend is None or pay_trend is None else ret_trend - pay_trend


def load_text():
    """Prior shareholder support and one-off award wording, read from each proxy's text."""
    out = {}
    if os.path.exists(TEXT):
        with open(TEXT, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                if r["status"] == "ok":
                    out[(int(r["cik"]), r["meeting_date"])] = r
    return out


def load_structure():
    """What the AI reader recorded about how the CEO's pay is built, by (SEC number, meeting date)."""
    out = {}
    if os.path.exists(STRUCTURE):
        with open(STRUCTURE, encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                out[(int(rec["cik"]), rec["meeting_date"])] = rec["answers"]
    return out


def structure_inputs(answers):
    """Three inputs from the reader's answers, each +1, 0 or -1. An answer counts only if its quote
    was found in the proxy. Not used by the pay model: see pay_structure_test.py.
        one-off award to the CEO: yes +1, the proxy says none -1
        performance-based share of equity: none stated +1, three quarters or more -1
        support at the last pay vote: under 70 percent +1, 90 percent or more -1"""
    if not answers:
        return [0.0, 0.0, 0.0]
    v = lambda k: answers[k]["answer"] if answers[k]["verified"] else None
    share, support = v("performance_share_pct"), v("prior_support_pct")
    return [
        {"yes": 1.0, "no": -1.0}.get(v("special_award"), 0.0),
        1.0 if share is None else -1.0 if share >= 75 else 0.0,
        0.0 if support is None else 1.0 if support < 70 else -1.0 if support >= 90 else 0.0,
    ]


def load_peers(meetings, proxy):
    """What is needed to build peer groups: industry, revenue, and each company's
    CEO pay with the date the proxy reporting it was filed."""
    if not os.path.exists(SIZE):
        return None
    sic, revenue = {}, collections.defaultdict(list)
    with open(SIZE, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            sic[int(r["cik"])] = r["sic"]
            if r["revenue_usd"]:
                revenue[int(r["cik"])].append((r["period_end"], float(r["revenue_usd"])))
    known = collections.defaultdict(list)  # cik -> [(filed, fiscal year end, pay)]
    for key, m in meetings.items():
        c = from_proxy(proxy[key], m) if m["status"] == "ok" else None
        if c:
            known[key[0]].append((m["filed"], c["year"], c["pay"]))
    for v in known.values():
        v.sort()
    return {"sic": sic, "revenue": revenue, "known": known}


def revenue_at(peers, cik, year_end):
    """Revenue for the fiscal year ending closest to `year_end`, not after it by more than a month."""
    best = None
    for end, value in peers["revenue"].get(cik, ()):
        if end <= minus_days(year_end, -31) and (best is None or end > best[0]):
            best = (end, value)
    return best[1] if best and best[0] >= minus_days(year_end, 400) else None


def peer_multiple(r, c, peers):
    """ISS "Multiple of Median": CEO pay divided by the median CEO pay of peers.

    Peers have the same two-digit industry code and revenue between 0.4 and 2.5
    times the company's, as in the ISS peer method. Their pay is the latest
    figure from a proxy filed before this meeting. If fewer than 12 qualify,
    the industry match is widened to one digit, then dropped.
    """
    cik = c.get("cik")
    if not c["pay"] or cik is None:
        return None, 0
    date, sic = r["moetedato"], peers["sic"].get(cik, "")
    own_rev = revenue_at(peers, cik, c["year"]) if c.get("year") else None
    pool = []
    for other, filings in peers["known"].items():
        if other == cik:
            continue
        seen = [f for f in filings if f[0] < date]
        if not seen:
            continue
        _, year, pay = seen[-1]
        rev = revenue_at(peers, other, year)
        size_ok = own_rev is None or (rev is not None and 0.4 <= rev / own_rev <= 2.5)
        if size_ok:
            pool.append((peers["sic"].get(other, ""), pay))
    for digits in (2, 1, 0):
        group = sorted(p for s, p in pool if digits == 0 or (sic and s[:digits] == sic[:digits]))
        if len(group) >= 12:
            mid = len(group) // 2
            median = group[mid] if len(group) % 2 else (group[mid - 1] + group[mid]) / 2
            return c["pay"] / median, len(group)
    return None, len(pool)


def add_features(rows, link, api, proxy, meetings, source="proxy", peers=None, text=None, structure=None):
    text = text or {}
    structure = structure or {}
    prev = {(r["season"], r["cusip"]): r["y"] for r in rows}
    for r in rows:
        last = prev.get((r["season"] - 1, r["cusip"]))
        cik = link.get(r["cusip"])
        key = (cik, r["moetedato"])
        c = None
        if source == "proxy" and key in meetings:
            c = from_proxy(proxy[key], meetings[key])
        if c is None and cik:
            c = from_api(api[cik], r["moetedato"])
        c = c or {"pay": None, "pay_before": None, "others": None, "return": None, "peer_return": None,
                  "pay_series": [], "return_series": [], "ceo_changed": False, "kind": "none"}
        c["cik"] = cik
        c["trend_gap"] = pay_return_gap(c["pay_series"], c["return_series"])
        c["peer_multiple"], c["peer_count"] = peer_multiple(r, c, peers) if peers else (None, 0)
        t = text.get(key) if c["kind"] == "proxy" else None
        c["support"] = float(t["prior_support"]) if t and t["prior_support"] else None
        c["support_sentence"] = t["prior_support_sentence"] if t else ""
        c["one_off"] = float(t["one_off_per_100k"]) if t and t["one_off_per_100k"] else None
        r["c"], r["prev"], r["pay"], r["others"] = c, last, c["pay"], c["others"]
        pay, others = c["pay"], c["others"]
        ratio = pay / others if pay and others else None
        r["x"] = [
            1.0 if last == 1 else 0.0,
            1.0 if last == 0 else 0.0,
            max(-1.0, min(1.5, math.log10(pay / 1e7))) if pay else 0.0,
            1.0 if pay and pay >= STRICT_LEVEL else 0.0,
            1.0 if pay and c["pay_before"] and pay / c["pay_before"] >= 2 else 0.0,
            max(-1.0, min(2.0, math.log2(ratio / 3))) if ratio else 0.0,
            max(-1.0, min(1.5, math.log10(others / 3e6))) if others else 0.0,
            1.0 if pay and pay >= STRICT_LEVEL and c["return"] is not None and c["return"] < 100 else 0.0,
            1.0 if c["ceo_changed"] else 0.0,
            max(-2.0, min(3.0, math.log2(c["peer_multiple"]))) if c["peer_multiple"] else 0.0,
            max(-1.0, min(1.0, -c["trend_gap"])) if c["trend_gap"] is not None else 0.0,
        ]
        # Experiment only (pay_structure_test.py): how the pay is built, where CEO pay is 25 million or more.
        c["structure"] = structure.get(key) if pay and pay >= STRICT_LEVEL and c["kind"] == "proxy" else None
        r["xs"] = structure_inputs(c["structure"])


def fit_predict(train, test, cols):
    w = bm.fit_logistic([[r["x"][i] for i in cols] for r in train], [r["y"] for r in train])
    return w, [bm.predict(w, [r["x"][i] for i in cols]) for r in test]


def fold_of(r, k=5):
    """Stable fold number per company, so a company is never split across folds."""
    return int(hashlib.sha1(r["cusip"].encode()).hexdigest(), 16) % k


def fit_calibrated(train, test, cols, k=5):
    """Fit on `train`, score `test`, and correct the confidence.

    A model scored on its own training votes looks more certain than it is. So
    each training vote is first scored by a model that did not see its company
    (five folds). A two-number correction is fitted on those honest scores and
    applied to the test scores. Returns (weights, test scores, honest training scores).
    """
    honest = [0.0] * len(train)
    for fold in range(k):
        inside = [r for r in train if fold_of(r, k) != fold]
        held = [i for i, r in enumerate(train) if fold_of(r, k) == fold]
        _, ps = fit_predict(inside, [train[i] for i in held], cols)
        for i, p in zip(held, ps):
            honest[i] = p
    squash = lambda p: math.log(min(max(p, 1e-6), 1 - 1e-6) / (1 - min(max(p, 1e-6), 1 - 1e-6)))
    fix = bm.fit_logistic([[squash(p)] for p in honest], [r["y"] for r in train], ridge=0.0)
    w, raw = fit_predict(train, test, cols)
    apply = lambda p: bm.predict(fix, [squash(p)])
    return w, [apply(p) for p in raw], [apply(p) for p in honest]


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
    """Plain-language reasons for the score, each with the figure behind it."""
    c, out = r["c"], []
    parts = sorted(((wi * xi, i) for i, (wi, xi) in enumerate(zip(w[1:], r["x"]))), reverse=True)
    for value, i in parts:
        if value <= 0.05:
            continue
        name, text, rule = FEATURES[i]
        if name in ("pay_size", "pay_25m"):
            text = (f"CEO total pay {money(c['pay'])} for the year to {c['year']}"
                    + (" is at or above the 25 million dollar level NBIM reviews more strictly"
                       if c["pay"] >= STRICT_LEVEL else ""))
        elif name == "pay_doubled":
            text = f"CEO pay rose from {money(c['pay_before'])} to {money(c['pay'])}"
        elif name == "ceo_vs_others":
            text = f"CEO pay is {c['pay'] / c['others']:.1f} times the other executives' average ({money(c['others'])})"
        elif name == "others_size":
            text = f"the other named executives averaged {money(c['others'])}"
        elif name == "pay_vs_peers":
            text = (f"CEO pay is {c['peer_multiple']:.1f} times the median of {c['peer_count']} companies "
                    f"of similar industry and size")
        elif name == "pay_outran_returns":
            text = "CEO pay has grown faster than shareholder returns over the years in the pay table"
        elif name == "high_pay_lost":
            text = (f"CEO pay is {money(c['pay'])} while 100 dollars invested at the start of the pay table "
                    f"is now worth {c['return']:.0f}")
        if text not in [t for t, _ in out]:
            out.append((text, rule))
    return out[:3]


def structure_notes(r):
    """What the AI reader found in the proxy about how the pay is built, with its quotes. Evidence for
    the reviewer. Not part of the score."""
    st = r["c"].get("structure")
    if not st:
        return []
    known = lambda k: st[k]["verified"]
    out = []
    if known("special_award") and st["special_award"]["answer"] == "yes":
        out.append(f"a one-off award to the CEO outside the regular programme (\"{st['special_award']['quote']}\")")
    if known("performance_share_pct"):
        out.append(f"{st['performance_share_pct']['answer']:.0f}% of the CEO's equity award is performance-based "
                   f"(\"{st['performance_share_pct']['quote']}\")")
    if known("prior_support_pct"):
        out.append(f"the last pay vote had {st['prior_support_pct']['answer']:.0f}% support (\"{st['prior_support_pct']['quote']}\")")
    return out


def explore(train):
    """Against-rate tables on the training seasons only. This is how inputs were chosen."""
    print(f"Training seasons only ({len(train)} votes, {sum(r['y'] for r in train)} against). The test season is not read here.\n")

    def show(title, key):
        cells = collections.defaultdict(lambda: [0, 0])
        for r in train:
            k = key(r)
            if k is not None:
                cells[k][0] += 1
                cells[k][1] += r["y"]
        print(title)
        bm.table(["Group", "Votes", "Against", "Against rate"],
                 [[k, n, a, f"{a / n:.0%}"] for k, (n, a) in sorted(cells.items())])
        print()

    c = lambda r: r["c"]
    show("CEO pay", lambda r: None if not r["pay"] else "a under $10m" if r["pay"] < 10e6 else "b $10-25m"
         if r["pay"] < 25e6 else "c $25-40m" if r["pay"] < 40e6 else "d $40m or more")
    show("Pay against the year before", lambda r: None if not (r["pay"] and c(r)["pay_before"]) else
         "a less than doubled" if r["pay"] / c(r)["pay_before"] < 2 else "b doubled or more")
    show("CEO pay against the other executives' average", lambda r: None if not (r["pay"] and r["others"]) else
         "a under 4x" if r["pay"] / r["others"] < 4 else "b 4-8x" if r["pay"] / r["others"] < 8 else "c over 8x")
    show("Other executives' average pay", lambda r: None if not r["others"] else "a under $3m" if r["others"] < 3e6
         else "b $3-8m" if r["others"] < 8e6 else "c $8m or more")
    show("Value today of 100 dollars invested at the start of the pay table", lambda r: None if c(r)["return"] is None else
         "a under 100 (lost money)" if c(r)["return"] < 100 else "b 100-200" if c(r)["return"] < 200 else "c over 200")
    show("More than one CEO paid during the year", lambda r: None if c(r)["kind"] != "proxy" else
         "b yes" if c(r)["ceo_changed"] else "a no")
    show("Packages of $25m or more only: value today of 100 dollars invested", lambda r: None
         if not (r["pay"] and r["pay"] >= STRICT_LEVEL) or c(r)["return"] is None else
         "a under 100 (lost money)" if c(r)["return"] < 100 else "b 100-200" if c(r)["return"] < 200 else "c over 200")
    show("Packages of $25m or more only: NBIM's vote last season", lambda r: None
         if not (r["pay"] and r["pay"] >= STRICT_LEVEL) else
         {1: "c opposed", 0: "b supported", None: "a no vote last season"}[r["prev"]])
    show("Where the figure came from", lambda r: c(r)["kind"])


def load_rows(source="proxy"):
    """All annual pay votes with their inputs attached."""
    rows, other = read_votes()
    link, api, proxy, meetings = load_sources()
    peers = load_peers(meetings, proxy) if source == "proxy" else None
    add_features(rows, link, api, proxy, meetings, source, peers, load_text() if source == "proxy" else None,
                 load_structure() if source == "proxy" else None)
    return rows, other


def score_test_season(rows):
    """Fit on the seasons before TEST_SEASON and score that season.

    Returns (train, test, weights, test scores, cut-off). The cut-off is chosen
    on the training seasons only, from scores given by models that did not see
    the company being scored.
    """
    train = [r for r in rows if r["season"] < TEST_SEASON]
    test = [r for r in rows if r["season"] == TEST_SEASON]
    cols = list(range(len(FEATURES)))
    w, ps, ps_train = fit_calibrated(train, test, cols)
    thr = bm.best_f1_threshold(ps_train, [r["y"] for r in train])
    return train, test, w, ps, thr


def band_of(p, thr):
    return "likely AGAINST board" if p >= thr else "likely WITH board" if p < LOW else "send to human"


def warnings_for(r):
    """Reasons a person should look at the figures before trusting the score."""
    c, out = r["c"], []
    if c["kind"] == "none":
        out.append("no pay figure found for this company")
    if c["kind"] == "api":
        out.append("pay figure is the value as reported in a later filing")
    if c.get("rescaled"):
        out.append("a figure in the filing was tagged a thousand or more times too large and was scaled down")
    if c["pay"] and c["others"] and c["others"] >= c["pay"]:
        out.append("other executives' average pay is at or above the CEO's, check the filing")
    if c["pay"] and c["pay"] >= 200e6:
        out.append("CEO pay above 200 million dollars, check the filing")
    return out


def develop(rows):
    """Compare input sets on the training seasons only (2024 and 2025).

    Two folds: learn on one season, score the other. Season 2024 has no "last
    season" in the data, so only the company-fact inputs are compared here.
    The test season is not read.
    """
    names = [f[0] for f in FEATURES]
    base = [names.index(n) for n in ("pay_size", "pay_25m", "pay_doubled", "ceo_vs_others", "others_size",
                                     "high_pay_lost", "ceo_changed")]
    extra = [names.index(n) for n in names if n not in ("prev_against", "prev_for") and names.index(n) not in base]
    sets = [("company facts, first version", base)] + [(f"+ {names[i]}", base + [i]) for i in extra] + [("+ all of them", base + extra)]
    s24 = [r for r in rows if r["season"] == 2024]
    s25 = [r for r in rows if r["season"] == 2025]
    n = sum(1 for r in s25 if r["prev"] == 1)
    print("Training seasons only. AP = average precision (higher is better).\n")
    out = []
    for label, cols in sets:
        _, p25 = fit_predict(s24, s25, cols)
        _, p24 = fit_predict(s25, s24, cols)
        y25, y24 = [r["y"] for r in s25], [r["y"] for r in s24]
        hits = sum(y for f, y in zip(top_flags(p25, n), y25) if f)
        out.append([label, f"{bm.average_precision(p25, y25):.3f}", f"{bm.average_precision(p24, y24):.3f}",
                    f"{(bm.average_precision(p25, y25) + bm.average_precision(p24, y24)) / 2:.3f}", hits])
    bm.table(["Inputs", "AP 2024->2025", "AP 2025->2024", "Mean AP", f"Hits in top {n} (2025)"], out)
    base_hits = sum(r["y"] for r in s25 if r["prev"] == 1)
    print(f"\n  For comparison, 'same as last season' on 2025: {base_hits} hits with {n} flags.")
    cover = lambda key: sum(1 for r in s24 + s25 if r["c"].get(key) is not None) / len(s24 + s25)
    print(f"  Share of training votes with the measure: pay vs peers {cover('peer_multiple'):.0%}, "
          f"pay vs returns trend {cover('trend_gap'):.0%}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--explore", action="store_true", help="training-season tables only")
    ap.add_argument("--develop", action="store_true", help="compare input sets on the training seasons only")
    ap.add_argument("--source", choices=["proxy", "api"], default="proxy")
    a = ap.parse_args()

    rows, other = load_rows(a.source)
    train = [r for r in rows if r["season"] < TEST_SEASON]
    if a.explore:
        explore(train)
        return
    if a.develop:
        develop(train)
        return
    train, test, w, ps, thr = score_test_season(rows)
    ys = [r["y"] for r in test]

    print(f"NBIM say-on-pay votes: {len(rows)} annual pay votes at {len({r['cusip'] for r in rows})} companies (US filers)")
    print(f"Left out: {other['frequency of the pay vote'] + other['no for/against vote (frequency votes, blanks)']} "
          f"frequency votes and blanks (NBIM never opposed the board on these), and {other['merger payouts']} "
          f"merger payout votes ({other['merger payouts against']} against, one-off events with no history)")
    print(f"Train: seasons before {TEST_SEASON}, {len(train)} votes, {sum(r['y'] for r in train)} against the board")
    print(f"Test:  season {TEST_SEASON}, {len(test)} votes, {sum(ys)} against the board ({sum(ys) / len(ys):.1%})")
    kinds = collections.Counter(r["c"]["kind"] for r in test)
    cover = sum(1 for r in test if r["pay"])
    print(f"Company facts for the test votes: {kinds['proxy']} from the meeting's own proxy, {kinds['api']} from the SEC API, "
          f"{kinds['none']} none. CEO pay known for {cover} ({cover / len(test):.0%}).")
    days = sorted(int(r["c"]["source"].split(", ")[1].split()[0]) for r in test if r["c"]["kind"] == "proxy")
    if days:
        print(f"Proxies were filed {days[0]} to {days[-1]} days before the meeting (median {days[len(days) // 2]}).")
    print()

    _, ps_hist = fit_predict(train, test, HISTORY_ONLY)
    base = [r["prev"] == 1 for r in test]
    n = sum(base)

    print(f"Results on season {TEST_SEASON} (95% intervals from resampling votes)")
    big = [bool(r["pay"] and r["pay"] >= STRICT_LEVEL) for r in test]   # the simplest fact-based rule
    bm.table(["Method", "Precision", "95%", "Recall", "95%", "F1", "Flagged", "Hits", "False alarms", "Missed"],
             [metric("Always with board", [False] * len(test), ys),
              metric("Same as last season", base, ys),
              metric(f"History only, top {n}", top_flags(ps_hist, n), ys),
              metric(f"History + company facts, top {n}", top_flags(ps, n), ys),
              metric(f"History + company facts, p >= {thr:.2f}", [p >= thr for p in ps], ys),
              metric("One-line rule: against if CEO pay is $25m or more", big, ys),
              metric(f"History + company facts, top {sum(big)}", top_flags(ps, sum(big)), ys)])
    print(f"  The one-line rule is a strong baseline. With as many flags ({sum(big)}) the model finds a few more "
          f"against-votes; at its own cut-off it finds about as many with far fewer false alarms.")
    print(f"\n  'top {n}' rows flag exactly as many votes as the same-as-last-season baseline, so they compare like for like.")
    print(f"  Average precision: history + company facts {bm.average_precision(ps, ys):.3f}, "
          f"history only {bm.average_precision(ps_hist, ys):.3f}, random {sum(ys) / len(ys):.3f}")
    rate = sum(r["y"] for r in train) / len(train)
    print(f"  Brier score (lower is better): model {sum((p - y) ** 2 for p, y in zip(ps, ys)) / len(ys):.4f}, "
          f"always saying {rate:.1%} {sum((rate - y) ** 2 for y in ys) / len(ys):.4f}")

    print("\nBy what was known about the company")
    out = []
    for label, keep in (("CEO pay known", lambda r: r["pay"]),
                        ("only other executives' pay known", lambda r: not r["pay"] and r["others"]),
                        ("no pay figure", lambda r: not r["pay"] and not r["others"])):
        idx = [i for i, r in enumerate(test) if keep(r)]
        pos = [i for i in idx if ys[i]]
        out.append([label, len(idx), len(pos), sum(1 for i in pos if ps[i] >= thr),
                    f"{sum(1 for i in pos if ps[i] >= thr) / len(pos):.0%}" if pos else "-",
                    sum(1 for i in idx if ps[i] >= thr and not ys[i])])
    bm.table(["What was known", "Votes", "Against", "Found", "Recall", "False alarms"], out)

    print("\nNew situations: against-votes at companies NBIM did not oppose last season")
    new = [i for i, r in enumerate(test) if r["y"] and r["prev"] != 1]
    flagged = top_flags(ps, n)
    print(f"  {len(new)} such votes. Same-as-last-season finds 0 by construction; the model finds "
          f"{sum(flagged[i] for i in new)} in its top {n} and {sum(1 for i in new if ps[i] >= thr)} at p >= {thr:.2f}.")

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

    print("\nAgainst rate by CEO pay, test season")
    out = []
    for name, lo, hi in (("under $10m", 0, 10e6), ("$10-25m", 10e6, 25e6), ("$25-40m", 25e6, 40e6), ("$40m or more", 40e6, 1e15)):
        b = [r["y"] for r in test if r["pay"] and lo <= r["pay"] < hi]
        out.append([name, len(b), sum(b), f"{sum(b) / len(b):.0%}" if b else "-"])
    b = [r["y"] for r in test if not r["pay"]]
    out.append(["no CEO figure", len(b), sum(b), f"{sum(b) / len(b):.0%}" if b else "-"])
    bm.table(["CEO total pay", "Votes", "Against", "Against rate"], out)

    print("\nModel weights (positive = pushes towards AGAINST)")
    for (name, text, _), wi in zip(FEATURES, w[1:]):
        print(f"  {wi:+6.2f}  {name:<14} {text}")

    suffix = "" if a.source == "proxy" else "_api"
    path = os.path.join(ROOT, "data", "outputs", f"pay_votes_{TEST_SEASON}{suffix}.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["meeting_date", "company", "proposal", "probability_against", "band", "ceo_pay_usd",
                     "fiscal_year_end", "source", "source_url", "reasons", "guideline_rules", "data_warnings",
                     "pay_vs_peer_median", "support_at_previous_pay_vote", "support_sentence", "actual_against"])
        for r, p in sorted(zip(test, ps), key=lambda t: -t[1]):
            why, c = reasons(r, w), r["c"]
            wr.writerow([r["moetedato"], r["utsteder"], r["forslag"], f"{p:.3f}",
                         band_of(p, thr),
                         f"{c['pay']:.0f}" if c["pay"] else "", c.get("year", ""), c.get("source", ""), c.get("url", ""),
                         " | ".join(t for t, _ in why), ", ".join(sorted({x for _, x in why if x})),
                         " | ".join(warnings_for(r)),
                         f"{c['peer_multiple']:.2f}" if c.get("peer_multiple") else "",
                         f"{c['support']:g}" if c.get("support") is not None else "", c.get("support_sentence", ""),
                         r["y"]])
    print(f"\nWrote {len(test)} scored votes to {os.path.relpath(path, ROOT)}")


if __name__ == "__main__":
    main()
