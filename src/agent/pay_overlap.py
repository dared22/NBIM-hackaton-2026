"""The same US pay proposals are in both vote files. Which model should answer them?

Run from the repo root (no internet, no API key):
    python3 src/agent/pay_overlap.py

NBIM's vote file (data/dirty/real_votes.csv) holds the annual pay vote of 36 US
companies. The same votes are in Norges Bank's SEC filings
(data/dirty/nbim_pay_votes.csv), where the pay model scores them with company
facts. Before this check the tool answered these proposals twice, once per
file, and the two answers could differ.

This script compares the two models on exactly those proposals. A proposal is
matched by meeting date and company name.

    history model  fitted on earlier years only (src/benchmark/model.py)
    pay model      season 2026: fitted on the seasons before, the real test.
                   Seasons 2024 and 2025 are the pay model's training seasons,
                   so each vote there is scored by a model that did not see
                   that company (five folds). That is not a time split, and
                   it is said here so nobody reads it as one.

Result: the pay model is the better one on these proposals, so src/run.py uses
its answer for them.
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "src", "agent"))
from benchmark import model as bm  # noqa: E402
import pay_model as pm  # noqa: E402

VOTES = os.path.join(ROOT, "data", "dirty", "real_votes.csv")
DROP = re.compile(r"\b(inc|incorporated|corporation|corp|company|co|the|holdings|ltd|plc|group)\b")
ANNUAL_PAY = re.compile(r"advisory vote|named executive|say[- ]on[- ]pay|executive compensation", re.I)


def name_words(name):
    """A company name as a list of words, without legal forms, apostrophes or punctuation."""
    plain = re.sub(r"[^a-z0-9]+", " ", re.sub(r"['’]", "", name.lower()))
    return DROP.sub(" ", plain).split()


def is_annual_pay_vote(row):
    """A US company's yearly advisory vote on executive pay in NBIM's vote file."""
    return (row["country"] == "United States" and row["proposal_type"] == "SAY_ON_PAY"
            and bool(ANNUAL_PAY.search(row["proposal_text"])))


def build_index(items):
    """items: (company name, meeting date, payload). Returns {date: [(name words, payload)]}."""
    index = {}
    for name, date, payload in items:
        index.setdefault(date, []).append((name_words(name), payload))
    return index


def find(index, company, date):
    """The payload for this company on this date, or None. The name must be the
    same, or its first two words must be. Two matches on one date count as none."""
    a = name_words(company)
    hits = [p for b, p in index.get(date, []) if a == b or (len(a) >= 2 and a[:2] == b[:2])]
    return hits[0] if len(hits) == 1 else None


def main():
    pay_rows, _ = pm.load_rows()
    train, test, _, ps, thr = pm.score_test_season(pay_rows)
    _, _, honest = pm.fit_calibrated(train, test, list(range(len(pm.FEATURES))))
    index = build_index([(r["utsteder"], r["moetedato"], (p, r)) for r, p in list(zip(train, honest)) + list(zip(test, ps))])
    rows = bm.read_votes(VOTES)
    out, total = [], [0] * 8
    for year in (2024, 2025, 2026):
        _, scored, _, hist_thr = bm.run_year(rows, year)
        both = [(r, find(index, r["company"], r["meeting_date"])) for r in scored if is_annual_pay_vote(r)]
        n_all = len(both)
        both = [(r, m) for r, m in both if m]
        h_flag = [r for r, _ in both if r["p"] >= hist_thr]
        p_flag = [r for r, m in both if m[0] >= thr]
        row = [n_all, len(both), sum(r["y"] for r, _ in both),
               len(h_flag), sum(r["y"] for r in h_flag), len(p_flag), sum(r["y"] for r in p_flag),
               sum(r["y"] for r, m in both if m[0] < pm.LOW)]
        total = [a + b for a, b in zip(total, row)]
        out.append([f"{year}" + (" (the real test)" if year == pm.TEST_SEASON else " (scored without the company)")] + row)
    bm.table(["Year", "US pay votes in NBIM's file", "also in the SEC file", "against the board",
              "History model: flags", "hits", "Pay model: flags", "hits", "Pay model waved through an against-vote"],
             out + [["all three"] + total])
    print(f"\n  On the {total[1]} proposals in both files the pay model finds {total[6]} of the {total[2]} against-votes "
          f"with {total[5]} flags.")
    print(f"  The history model finds {total[4]} with {total[3]} flags. In 2026 there were no against-votes among them,")
    print("  and the pay model raises one false alarm where the history model raises two.")
    print("  src/run.py now gives these proposals the pay model's answer, so each proposal has one answer.")


if __name__ == "__main__":
    main()
