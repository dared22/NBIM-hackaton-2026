"""When should the tool ask a person? Confidence and routing on NBIM's vote file.

Run from the repo root (no internet, no API key, under a minute):
    python3 src/agent/routing.py

The case asks for a confidence and for unsure cases to go to a person. The
history model (src/benchmark/model.py) follows the board on its own when the
probability of an against-vote is below 5%. This script checks that choice.

    1. Is the confidence honest? Stated probability against what happened.
    2. Does a correction learned from earlier years make it more honest?
    3. What does a lower "ask a person" level cost, and what does it catch?
    4. Can anything in the vote file pick out the against-votes that the tool
       waves through? Two tests: wording never seen before, and another item
       at the same meeting that the tool is unsure about or flags.
    5. The case asks for three answers: for, against, abstain. When does NBIM
       abstain, and can the tool say so?

Every test year is scored by a model fitted on earlier years only. Questions
3 and 4 are judged on test years 2022-2025. 2026 is shown next to them and
was not used to choose anything.

Result: the 5% level is kept. Below it the tool is wrong about 2% of the
time, and none of the tests found a group where that share is clearly higher.
Abstaining is a market habit: in a few countries NBIM casts its against-votes
on directors as abstentions. abstain_markets() learns those from earlier years
and src/run.py uses it for the suggested vote.
"""

import collections
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))
from benchmark import model as bm  # noqa: E402

VOTES = os.path.join(ROOT, "data", "dirty", "real_votes.csv")
DEVELOP = range(2022, 2026)
FINAL = 2026
BINS = ((0, .02), (.02, .05), (.05, .10), (.10, .20), (.20, .40), (.40, .70), (.70, 1.01))
LEVELS = (0.05, 0.04, 0.03, 0.02)


def squash(p):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def corrected(runs, year, back=3):
    """The year's probabilities after a two-number correction fitted on the
    scores of up to `back` earlier test years (each scored by a model that had
    not seen that year)."""
    earlier = [r for y in range(max(min(runs), year - back), year) for r in runs[y][1]]
    fix = bm.fit_logistic([[squash(r["p"])] for r in earlier], [r["y"] for r in earlier], ridge=0.0)
    return [bm.predict(fix, [squash(r["p"])]) for r in runs[year][1]]


def abstain_markets(earlier, min_cases=2):
    """(country, proposal type) pairs where most of NBIM's earlier votes against
    the board were cast as abstentions. Needs at least `min_cases` such votes.
    Returns {pair: (abstentions, votes against the board)}."""
    seen = collections.defaultdict(lambda: [0, 0])
    for r in earlier:
        if r["y"]:
            c = seen[(r["country"], r["proposal_type"])]
            c[0] += r["nbim_vote"] == "AVSTÅ"
            c[1] += 1
    return {k: (a, n) for k, (a, n) in seen.items() if n >= min_cases and 2 * a > n}


def brier(ps, ys):
    return sum((p - y) ** 2 for p, y in zip(ps, ys)) / len(ys)


def share(k, n):
    return f"{k / n:.1%}" if n else "-"


def main():
    rows = bm.read_votes(VOTES)
    years = list(DEVELOP) + [FINAL]
    runs = {y: bm.run_year(rows, y) for y in [min(DEVELOP) - 1] + years}
    pooled = [r for y in years for r in runs[y][1]]

    print(f"1. Is the confidence honest? Test years {years[0]}-{years[-1]}, {len(pooled)} proposals")
    out = []
    for lo, hi in BINS:
        b = [r for r in pooled if lo <= r["p"] < hi]
        if b:
            out.append([f"{lo:.0%} to {min(hi, 1):.0%}", len(b), share(sum(r["p"] for r in b), len(b)),
                        share(sum(r["y"] for r in b), len(b))])
    bm.table(["The tool says", "Proposals", "Average stated", "Actually against the board"], out)
    print("   Below 10% the stated probability matches what happened. Between 10% and 70% the tool")
    print("   says more than what happened, so a stated 50% is closer to 40%.")

    print("\n2. Does a correction learned from earlier years help? (Brier score, lower is better)")
    out = []
    for y in years:
        test = runs[y][1]
        ys = [r["y"] for r in test]
        out.append([y, f"{brier([r['p'] for r in test], ys):.4f}", f"{brier(corrected(runs, y), ys):.4f}"])
    bm.table(["Test year", "As it is", "With correction"], out)
    better = sum(1 for _, a, b in out if float(b) < float(a))
    print(f"   The correction is better in {better} of {len(out)} years. It is not used.")

    print("\n3. The level below which the tool follows the board on its own")
    out = []
    for level in LEVELS:
        cells, dev = [], [0, 0, 0, 0]
        for y in years:
            test, thr = runs[y][1], runs[y][3]
            read = sum(1 for r in test if level <= r["p"] < thr)
            waved = [r for r in test if r["p"] < level]
            missed, against = sum(r["y"] for r in waved), sum(r["y"] for r in test)
            if y in DEVELOP:
                dev = [dev[0] + read, dev[1] + len(test), dev[2] + missed, dev[3] + against]
            else:
                cells = [share(read, len(test)), f"{missed} of {against}", share(missed, len(waved))]
        out.append([f"{level:.0%}", share(dev[0], dev[1]), f"{dev[2]} of {dev[3]} ({dev[2] / dev[3]:.0%})"] + cells)
    bm.table(["Level", f"{DEVELOP[0]}-{DEVELOP[-1]}: a person reads", "against-votes waved through",
              f"{FINAL}: a person reads", "against-votes waved through", "wrong among those waved through"], out)
    print(f"   Judged on {DEVELOP[0]}-{DEVELOP[-1]}: going from 5% to 3%, a person reads about 60% more proposals and")
    print("   most of the against-votes that were waved through still are. The gain in 2026 is larger,")
    print("   but the level may not be chosen on 2026. The 5% level is kept. The level is a choice between")
    print("   reading time and missed against-votes, and this table is what to choose from.")

    print("\n4. Can anything pick out the against-votes among the proposals the tool waves through (below 5%)?")
    groups = {name: collections.defaultdict(lambda: [0, 0]) for name in ("wording", "meeting")}
    for y in years:
        train, test, _, thr = runs[y]
        seen = collections.Counter(r["text_key"] for r in train)
        by_meeting = collections.defaultdict(list)
        for r in test:
            by_meeting[r["meeting_id"]].append(r)
        period = f"{DEVELOP[0]}-{DEVELOP[-1]}" if y in DEVELOP else str(FINAL)
        for r in test:
            if r["p"] >= bm.LOW:
                continue
            others = by_meeting[r["meeting_id"]]
            kind = "director election" if r["proposal_type"] == "DIRECTOR_ELECTION" else "other proposal"
            n = seen[r["text_key"]]
            wording = kind + (", wording never seen" if n == 0 else ", wording seen 1-4 times" if n < 5 else ", wording seen 5 or more times")
            meeting = ("the tool flags another item at the meeting" if any(o["p"] >= thr for o in others)
                       else "the tool is unsure about another item" if any(o["p"] >= bm.LOW for o in others)
                       else "nothing else stands out at the meeting")
            for name, key in (("wording", wording), ("meeting", meeting)):
                c = groups[name][(key, period)]
                c[0] += 1
                c[1] += r["y"]
    for name in ("wording", "meeting"):
        out = []
        for key in sorted({k for k, _ in groups[name]}):
            row = [key]
            for period in (f"{DEVELOP[0]}-{DEVELOP[-1]}", str(FINAL)):
                n, k = groups[name][(key, period)]
                row += [n, k, share(k, n)]
            out.append(row)
        bm.table(["Group", f"{DEVELOP[0]}-{DEVELOP[-1]}: proposals", "against", "share", f"{FINAL}: proposals", "against", "share"], out)
    print(f"   No group stands out enough to send to a person: in {DEVELOP[0]}-{DEVELOP[-1]} the share of against-votes is")
    print("   between 0.5% and 3.4% in every group, and the order of the groups changes between the periods.")
    print("   The against-votes the tool waves through look like the other proposals in the vote file.")

    print("\n5. Abstain. Of NBIM's votes against the board, how many were cast as abstentions, and does")
    print("   the market habit learned from earlier years say so? (given that the vote is against the board)")
    year_of = lambda r: int(r["meeting_date"][:4])
    out, total = [], [0, 0, 0, 0]
    for y in [min(DEVELOP) - 1] + years:
        markets = abstain_markets([r for r in rows if year_of(r) < y])
        against = [r for r in rows if year_of(r) == y and r["y"]]
        said = [r for r in against if (r["country"], r["proposal_type"]) in markets]
        row = [len(against), sum(r["nbim_vote"] == "AVSTÅ" for r in against), len(said), sum(r["nbim_vote"] == "AVSTÅ" for r in said)]
        total = [a + b for a, b in zip(total, row)]
        out.append([y] + row)
    bm.table(["Year", "Votes against the board", "cast as abstain", "Rule says abstain", "of which right"], out + [["all"] + total])
    everything = abstain_markets(rows)
    print("   Markets with the habit over the whole file: " + ", ".join(
        f"{c} {t.lower().replace('_', ' ')} ({a} of {n})" for (c, t), (a, n) in sorted(everything.items())))
    print(f"   In {FINAL} the rule finds none of that year's abstentions: they are in markets with no such history.")
    print("   Other abstentions in the file are on items with no board recommendation (Brazil, cumulative")
    print("   voting), which have no 'against the board' answer and are outside the target.")


if __name__ == "__main__":
    main()
