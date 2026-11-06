"""Main's say-on-pay model (src/agent/pay_model.py on main), scored walk-forward for this branch's pipeline.

Will NBIM vote against the board on a US company's executive pay? A logistic model on NBIM's say-on-pay
votes from Norges Bank's own SEC Form N-PX filings (CIK 1374170, seasons 2024-2026: meetings July 2023 to
June 2026), with pay facts read from each meeting's own proxy statement. The inputs, the 25 million dollar
level, the two ISS measures, the confidence correction and the cut-off rule are main's, unchanged; see
main's docstring for how they were chosen (on main's training seasons 2024-2025).

Two changes from main, both to avoid look-ahead in this pipeline:
  - Walk-forward by calendar year, as the rest of this branch: the model for year Y is fitted on N-PX votes
    at meetings before 1 January Y and scores the meetings in Y. Main fits once on seasons 2024-2025.
  - Proxy figures only. Main falls back to SEC API figures "as reported in 2026" where no proxy was read;
    that is a later value, so here such votes get no pay figure (0 on every pay input, as main does for
    a missing figure).

Data (copied from main)
    data/dirty/nbim_pay_votes.csv            NBIM's say-on-pay votes from N-PX
    data/evidence/main/proxy_pay.csv         tagged pay figures from each proxy
    data/evidence/main/proxy_meetings.csv    which proxy belongs to which meeting (filing date checked)
    data/evidence/main/pay_company_link.csv  CUSIP and company name to SEC number
    data/evidence/main/company_size.csv      industry and revenue, for the peer groups
    data/evidence/main/proxy_text.csv        support at the last pay vote, read from the proxy text (main's rule 3.3.5 note)

    python -m nbim_vote.pay_model     # walk-forward on all N-PX pay votes, 2024-2026
"""

import collections
import csv
import datetime
import hashlib
import itertools
import math
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VOTES = ROOT / "data" / "dirty" / "nbim_pay_votes.csv"
MAIN = ROOT / "data" / "evidence" / "main"
STRICT_LEVEL = 25e6  # NBIM's own voting review: a stricter assessment of US packages of this size or more
LOW = 0.05           # main's band: below this, "likely with the board"
FIRST_YEAR = 2024    # the first calendar year with earlier N-PX votes to fit on

FEATURES = [  # main's inputs: name, plain-language description, NBIM guideline rule
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


def _read(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


# ------------------------------------------------------------------ main's logistic model (src/benchmark/model.py)
def _solve(a, b):
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
        grad, hess = [0.0] * d, [[0.0] * d for _ in range(d)]
        for x, y in zip(xs, ys):
            v = [1.0] + x
            p = 1.0 / (1.0 + math.exp(-sum(wi * vi for wi, vi in zip(w, v))))
            s = p * (1.0 - p)
            for i in range(d):
                grad[i] += (p - y) * v[i]
                for j in range(i, d):
                    hess[i][j] += v[i] * s * v[j]
        for i in range(d):
            for j in range(i):
                hess[i][j] = hess[j][i]
            if i:
                grad[i] += ridge * w[i]
                hess[i][i] += ridge
        step = _solve(hess, grad)
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
    return p, r, 2 * p * r / (p + r) if p + r else 0.0


def best_f1_threshold(ps, ys):
    best = (0.0, 0.5)
    for t in sorted(set(ps)):
        f1 = prf([p >= t for p in ps], ys)[2]
        if f1 > best[0]:
            best = (f1, t)
    return best[1]


def average_precision(ps, ys):
    hits, seen, total = 0, 0, 0.0
    for _, group in itertools.groupby(sorted(zip(ps, ys), key=lambda t: -t[0]), key=lambda t: t[0]):
        labels = [y for _, y in group]
        hits += sum(labels)
        seen += len(labels)
        total += sum(labels) * hits / seen
    return total / hits if hits else 0.0


# ------------------------------------------------------------------ main's inputs
def read_votes():
    """Annual say-on-pay votes, one row per vote (main's filter: no frequency votes, no merger payouts)."""
    seen, rows = set(), []
    for r in _read(VOTES):
        key = tuple(r.values())
        if key in seen:
            continue
        seen.add(key)
        text = r["forslag"].lower()
        if r["stemme"] not in ("FOR", "AGAINST", "WITHHOLD") or "frequency" in text:
            continue
        if re.search(r"merger|golden parachute|transaction|in connection with|business combination|arrangement", text):
            continue
        r["y"] = 1 if r["for_eller_mot_ledelsen"] == "AGAINST" else 0
        r["season"] = int(r["innsendt"][:4])
        rows.append(r)
    rows.sort(key=lambda r: (r["moetedato"], r["cusip"], r["forslag"]))
    return rows


def _repaired(value, limit):
    """A few filings tag a figure a thousand times too large; divide until it is below `limit` (main)."""
    while value >= limit:
        value /= 1000.0
    return value


def from_proxy(facts, meeting):
    """Pay facts from the proxy filed before this meeting, or None (main's from_proxy)."""
    by_year = collections.defaultdict(list)
    for f in facts["PeoTotalCompAmt"]:
        if float(f["value"]) > 0:
            by_year[f["period_end"]].append(f)
    if not by_year or meeting["filed"] >= meeting["meeting_date"]:
        return None
    years = sorted(by_year, reverse=True)
    pay_in = lambda year: max(_repaired(float(f["value"]), 1e9) for f in by_year[year])

    def at(tag, year, limit):
        vals = [_repaired(float(f["value"]), limit) for f in facts[tag] if f["period_end"] == year and float(f["value"]) > 0]
        return max(vals) if vals else None

    return {
        "pay": pay_in(years[0]), "pay_before": pay_in(years[1]) if len(years) > 1 else None,
        "others": at("NonPeoNeoAvgTotalCompAmt", years[0], 1e9), "return": at("TotalShareholderRtnAmt", years[0], 1e5),
        "pay_series": [pay_in(y) for y in reversed(years)],
        "return_series": [at("TotalShareholderRtnAmt", y, 1e5) for y in reversed(years)],
        "ceo_changed": len({f["person"] for f in by_year[years[0]] if f["person"]}) > 1,
        "year": years[0], "filed": meeting["filed"], "url": meeting["url"],
    }


def pay_return_gap(pay, ret):
    """ISS "Pay-TSR Alignment" (main): trend of shareholder return minus trend of CEO pay. Needs three years."""
    n = len(pay)
    if n < 3 or any(v is None for v in ret) or len(ret) != n:
        return None

    def trend(xs, ys, ws):
        sw, swx, swy = sum(ws), sum(w * x for w, x in zip(ws, xs)), sum(w * y for w, y in zip(ws, ys))
        swxy, swxx = sum(w * x * y for w, x, y in zip(ws, xs, ys)), sum(w * x * x for w, x in zip(ws, xs))
        den = sw * swxx - swx * swx
        return ((sw * swxy - swx * swy) / den) / (swy / sw) if den and swy else None

    ret_trend = trend(range(n + 1), [100.0] + list(ret), [0.85 ** (n - i) for i in range(n + 1)])
    pay_trend = trend(range(1, n + 1), pay, [0.85 ** (n - i + 0.5) for i in range(1, n + 1)])
    return None if ret_trend is None or pay_trend is None else ret_trend - pay_trend


def _minus_days(date, days):
    return (datetime.date.fromisoformat(date) - datetime.timedelta(days=days)).isoformat()


def _revenue_at(peers, cik, year_end):
    best = None
    for end, value in peers["revenue"].get(cik, ()):
        if end <= _minus_days(year_end, -31) and (best is None or end > best[0]):
            best = (end, value)
    return best[1] if best and best[0] >= _minus_days(year_end, 400) else None


def peer_multiple(date, cik, c, peers):
    """ISS "Multiple of Median" (main): CEO pay over the median CEO pay of peers, from proxies filed before `date`."""
    if not c["pay"] or cik is None:
        return None, 0
    sic = peers["sic"].get(cik, "")
    own_rev = _revenue_at(peers, cik, c["year"])
    pool = []
    for other, filings in peers["known"].items():
        seen = [f for f in filings if f[0] < date] if other != cik else []
        if not seen:
            continue
        _, year, pay = seen[-1]
        rev = _revenue_at(peers, other, year)
        if own_rev is None or (rev is not None and 0.4 <= rev / own_rev <= 2.5):
            pool.append((peers["sic"].get(other, ""), pay))
    for digits in (2, 1, 0):
        group = sorted(p for s, p in pool if digits == 0 or (sic and s[:digits] == sic[:digits]))
        if len(group) >= 12:
            mid = len(group) // 2
            return c["pay"] / (group[mid] if len(group) % 2 else (group[mid - 1] + group[mid]) / 2), len(group)
    return None, len(pool)


@lru_cache(maxsize=1)
def load_rows():
    """Every N-PX pay vote with main's inputs attached (r["x"]), its SEC number and its pay facts."""
    rows = read_votes()
    link = {r["cusip"]: int(r["cik"]) for r in _read(MAIN / "pay_company_link.csv") if r["status"] == "linked"}
    meetings = {(int(r["cik"]), r["meeting_date"]): r for r in _read(MAIN / "proxy_meetings.csv")}
    proxy = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in _read(MAIN / "proxy_pay.csv"):
        proxy[(int(r["cik"]), r["meeting_date"])][r["tag"]].append(r)
    sic, revenue = {}, collections.defaultdict(list)
    for r in _read(MAIN / "company_size.csv"):
        sic[int(r["cik"])] = r["sic"]
        if r["revenue_usd"]:
            revenue[int(r["cik"])].append((r["period_end"], float(r["revenue_usd"])))
    known = collections.defaultdict(list)  # cik -> [(filed, fiscal year end, CEO pay)]
    for key, m in meetings.items():
        c = from_proxy(proxy[key], m) if m["status"] == "ok" else None
        if c:
            known[key[0]].append((m["filed"], c["year"], c["pay"]))
    for v in known.values():
        v.sort()
    peers = {"sic": sic, "revenue": revenue, "known": known}
    text = {(int(r["cik"]), r["meeting_date"]): r for r in _read(MAIN / "proxy_text.csv") if r["status"] == "ok"}

    prev = {(r["season"], r["cusip"]): r["y"] for r in rows}  # NBIM's vote at last season's meeting
    empty = {"pay": None, "pay_before": None, "others": None, "return": None, "pay_series": [], "return_series": [], "ceo_changed": False}
    for r in rows:
        last, cik = prev.get((r["season"] - 1, r["cusip"])), link.get(r["cusip"])
        key = (cik, r["moetedato"])
        c = (from_proxy(proxy[key], meetings[key]) if key in meetings else None) or dict(empty)
        gap = pay_return_gap(c["pay_series"], c["return_series"])
        multiple, count = peer_multiple(r["moetedato"], cik, c, peers)
        t = text.get(key) if c["pay"] else None
        c.update(cik=cik, trend_gap=gap, peer_multiple=multiple, peer_count=count,
                 support=float(t["prior_support"]) if t and t["prior_support"] else None)
        pay, others = c["pay"], c["others"]
        ratio = pay / others if pay and others else None
        r["cik"], r["c"], r["prev"] = cik, c, last
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
            max(-2.0, min(3.0, math.log2(multiple))) if multiple else 0.0,
            max(-1.0, min(1.0, -gap)) if gap is not None else 0.0,
        ]
    return rows


def _fold(r, k=5):
    return int(hashlib.sha1(r["cusip"].encode()).hexdigest(), 16) % k


def _squash(p):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def fit_calibrated(train, test, k=5):
    """Main's fit: weights on `train`, confidence corrected on company-held-out scores, cut-off from those
    honest scores. Returns (weights, corrected test scores, cut-off)."""
    honest = [0.0] * len(train)
    for fold in range(k):
        inside = [r for r in train if _fold(r, k) != fold]
        w = fit_logistic([r["x"] for r in inside], [r["y"] for r in inside])
        for i, r in enumerate(train):
            if _fold(r, k) == fold:
                honest[i] = predict(w, r["x"])
    fix = fit_logistic([[_squash(p)] for p in honest], [r["y"] for r in train], ridge=0.0)
    w = fit_logistic([r["x"] for r in train], [r["y"] for r in train])
    apply = lambda p: predict(fix, [_squash(p)])
    return w, [apply(predict(w, r["x"])) for r in test], best_f1_threshold([apply(p) for p in honest], [r["y"] for r in train])


@lru_cache(maxsize=None)
def score_year(year):
    """{(SEC number, meeting date): (p against, cut-off, row, weights)} for the N-PX pay votes at meetings in `year`,
    from a model fitted on votes at meetings before 1 January `year`. Empty before FIRST_YEAR."""
    if year < FIRST_YEAR:
        return {}
    rows = load_rows()
    start = f"{year}-01-01"
    train = [r for r in rows if r["moetedato"] < start]
    test = [r for r in rows if start <= r["moetedato"] < f"{year + 1}-01-01"]
    if not train or not test or not sum(r["y"] for r in train):
        return {}
    w, ps, cut = fit_calibrated(train, test)
    out = {}
    for r, p in zip(test, ps):
        if r["cik"] is not None:
            key = (r["cik"], r["moetedato"])
            if key not in out or p > out[key][0]:
                out[key] = (p, cut, r, w)
    return out


class PayModel:
    """Main's pay score for a proposal in this branch's data: US say-on-pay votes linked to an N-PX vote."""

    def __init__(self, known):
        self.known = known  # company_facts.CompanyFacts: company name to SEC number

    def lookup(self, row):
        """(p against, cut-off, N-PX row, weights) or None."""
        if row["country"] != "United States" or row["proposal_type"] != "SAY_ON_PAY":
            return None
        from nbim_vote.company_facts import norm_company
        cik = self.known.cik_by_name.get(norm_company(row["company"]))
        return score_year(int(row["meeting_date"][:4])).get((int(cik), row["meeting_date"])) if cik else None

    def signal(self, row):
        """'MOT' when the score is at or above the model's own cut-off, 'review' at or above LOW, else None."""
        d = self.decision(row)
        return d["signal"] if d else None

    def decision(self, row):
        """{signal, p, cut, rule, reasons} for a linked US say-on-pay vote, or None.
        rule: the guideline rule (3.3.x) of the input that pushed the score up the most, cited on MOT."""
        hit = self.lookup(row)
        if hit is None:
            return None
        p, cut, r, w = hit
        why = reasons(r, w)
        return {"signal": "MOT" if p >= cut else "review" if p >= LOW else None, "p": p, "cut": cut,
                "rule": next((g.replace("GVG ", "") for _, g in why if g), "3.3.8"),
                "reasons": [t for t, _ in why], "source_url": r["c"].get("url", "")}


def _money(v):
    return f"${v / 1e6:.1f}m"


def reasons(r, w):
    """Main's reasons: the inputs that pushed the score up the most, in plain words, with their rule."""
    c, out = r["c"], []
    for value, i in sorted(((wi * xi, i) for i, (wi, xi) in enumerate(zip(w[1:], r["x"]))), reverse=True):
        if value <= 0.05:
            continue
        name, text, rule = FEATURES[i]
        if name in ("pay_size", "pay_25m"):
            text = f"CEO total pay {_money(c['pay'])} for the year to {c['year']}" + (
                " is at or above the 25 million dollar level NBIM reviews more strictly" if c["pay"] >= STRICT_LEVEL else "")
        elif name == "pay_doubled":
            text = f"CEO pay rose from {_money(c['pay_before'])} to {_money(c['pay'])}"
        elif name == "ceo_vs_others":
            text = f"CEO pay is {c['pay'] / c['others']:.1f} times the other executives' average ({_money(c['others'])})"
        elif name == "others_size":
            text = f"the other named executives averaged {_money(c['others'])}"
        elif name == "pay_vs_peers":
            text = f"CEO pay is {c['peer_multiple']:.1f} times the median of {c['peer_count']} companies of similar industry and size"
        elif name == "high_pay_lost":
            text = f"CEO pay is {_money(c['pay'])} while 100 dollars invested at the start of the pay table is now worth {c['return']:.0f}"
        if text not in [t for t, _ in out]:
            out.append((text, rule))
    return out[:3]


def main():
    rows = load_rows()
    print("Main's pay model, walk-forward by calendar year on NBIM's N-PX say-on-pay votes (fitted on earlier meetings only).\n")
    print("| Year | Votes | Against | Fitted on | AP | AP, NBIM's vote last season only | Precision at cut-off | Recall at cut-off | Cut-off |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for year in (2024, 2025, 2026):
        scored = score_year(year)
        test = [r for r in rows if r["moetedato"][:4] == str(year)]
        ps = {id(v[2]): v[0] for v in scored.values()}
        test = [r for r in test if id(r) in ps]
        ys = [r["y"] for r in test]
        p = [ps[id(r)] for r in test]
        cut = next(iter(scored.values()))[1]
        prec, rec, _ = prf([x >= cut for x in p], ys)
        n_train = sum(1 for r in rows if r["moetedato"] < f"{year}-01-01")
        print(f"| {year} | {len(test)} | {sum(ys)} | {n_train} | {average_precision(p, ys):.3f} | "
              f"{average_precision([r['x'][0] for r in test], ys):.3f} | {prec:.1%} | {rec:.1%} | {cut:.2f} |")


if __name__ == "__main__":
    main()
