"""The combined model: both teams' systems in one score, for NBIM's vote file (all countries).

Run from the repo root (no internet, no API key, about a minute):
    python3 src/agent/combined_model.py

What goes in, for every proposal
    From main
        history      the history model's probability (src/benchmark/model.py)
        director     a director signal fired (NBIM rule + facts read from the US proxy), and
                     whether that signal has earned trust (src/agent/board_rules.py)
        wording      a wording rule says "against the board" (src/agent/proposal_rules.py)
    From Marie's pipeline (branch marie, exported by src/agent/export_jev_components.py)
        Jev          the Jev decision model's vote and its probability. Jev is given the
                     proposal, the guidelines in force, NBIM's earlier votes at the company and
                     company facts (US, Japan, Korea), and names a guideline
        second model her gradient-boosted model on vote history and company facts, trained on
                     earlier years only

    The exported file holds scores only: no NBIM vote, no rationale.

    The judge (src/agent/judge.py)
        judge        for US director nominees with proxy facts, an AI model is given the facts,
                     NBIM's rules and how often NBIM has followed each rule that applies, with
                     no names, and returns a probability, a rule and a reason

How they are combined
    One logistic regression with seven inputs, fitted on the years before the year being
    scored. A nominee the judge has answered is scored by a second, smaller regression on
    two inputs: the history model and the judge. Every input for a year was itself produced without that year's votes. The level
    at which the tool says "against" is chosen on earlier years too, each scored by a fit
    that did not include it.

How it was designed, and what that means for 2026
    The seven inputs are simply both systems' signals side by side. That choice, and the
    decision rule, were made on 2022-2025 only (the comparison below). 2026 was then scored
    once. But 2026 is not a clean test of the pieces: Marie's notes say her design was
    final only after she had seen 2026, and main's rule patterns were written with all
    years visible. Her cleanest years are 2022 and 2023 (Jev run once, after the design was
    fixed), so the per-year table matters more than the 2026 line.

Target: NBIM voted against the board's recommendation. Jev and the second model predict
"NBIM voted MOT", so on proposals the board recommends against, their probability is turned
around.
"""

import collections
import csv
import math
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "src", "agent"))
from benchmark import model as bm  # noqa: E402
import board_rules as br  # noqa: E402
import country_rules as cr  # noqa: E402
import judge as jg  # noqa: E402
import proposal_rules as pr  # noqa: E402

VOTES = os.path.join(ROOT, "data", "dirty", "real_votes.csv")
COMPONENTS = os.path.join(ROOT, "data", "evidence", "jev_pipeline", "components_{year}.csv")
FIRST = 2021                       # first year with a saved Jev run
DEVELOP = (2022, 2023, 2024, 2025)
FINAL = 2026
LOW = bm.LOW                       # below this the tool follows the board on its own
INPUTS = [
    ("history", "the history model's probability"),
    ("second_model", "the second model's probability (vote history and company facts)"),
    ("jev_probability", "the Jev decision model's probability"),
    ("jev_against", "Jev recommends a vote against the board"),
    ("director_signal", "a director rule applies (facts read from the proxy)"),
    ("director_trusted", "a director rule applies that NBIM has been following"),
    ("wording_rule", "a wording rule says against the board"),
    ("judge", "the judge model's probability, where it has proxy facts to weigh (US director nominees)"),
    ("judge_present", "the judge model gave an answer"),
]


def logit(p):
    p = min(max(p, 1e-3), 1 - 1e-3)
    return math.log(p / (1 - p))


def load_components(year):
    """Marie's exported scores for one year, by (meeting, item). No votes in this file."""
    with open(COMPONENTS.format(year=year), encoding="utf-8", newline="") as f:
        return {(r["meeting_id"], r["item_no"]): r for r in csv.DictReader(f)}


_JUDGE = []


def judge_answer(row, director):
    """The judge model's cached answer for a US director nominee ({"p", "rule", "reason"}), or None."""
    if not director:
        return None
    if not _JUDGE:
        _JUDGE.append(jg.load_cache())
    state = jg.director_state(row, director)
    return _JUDGE[0].get(jg.state_key(f"{row['meeting_id']}-{row['item_no']}", state)) if state else None


def judge_probability(row, director):
    answer = judge_answer(row, director)
    return answer["p"] if answer else None


def inputs_for(row, comp, director, worded, judge_p=None):
    """The inputs for one proposal. `row` must carry the history model's probability in row["p"]."""
    board_against = row["mgmt_rec"] == "MOT"
    jev_p, second_p = float(comp["jev_p_mot"]), float(comp["triage_p"])
    if board_against:                      # NBIM voting FOR is then the vote against the board
        jev_p, second_p = 1 - jev_p, 1 - second_p
        jev_against = comp["jev_vote"] == "FOR"
    else:
        jev_against = comp["jev_vote"] in ("MOT", "AVSTÅ")
    return [logit(row["p"]), logit(second_p), logit(jev_p), float(jev_against),
            float(bool(director and director["signals"])), float(bool(director and director["acts_alone"])),
            float(bool(worded)), logit(judge_p) if judge_p is not None else 0.0, float(judge_p is not None)]


def rule_tables():
    directors = {(r["meeting_id"], r["item_no"]): r for r in br.load_scored()}
    worded = {(r["meeting_id"], r["item_no"]): r for r in pr.load_scored() if r["rules"]}
    return directors, worded


def year_data(rows, year, directors, worded):
    """Every proposal of one year with its inputs, scored by a history model fitted on earlier years."""
    _, test, _, hist_thr = bm.run_year(rows, year)
    comp = load_components(year)
    out = []
    for r in test:
        k = (r["meeting_id"], r["item_no"])
        if k in comp:
            r["comp"], r["hist_thr"] = comp[k], hist_thr
            r["director"], r["worded"] = directors.get(k), worded.get(k)
            r["country_fact"] = cr.signal_for(r)
            r["judge_p"] = judge_probability(r, r["director"])
            r["xc"] = inputs_for(r, comp[k], r["director"], r["worded"], r["judge_p"])
            out.append(r)
    return out


SHARED = list(range(7))      # the seven inputs every proposal has
JUDGED = [0, 7]              # for a nominee the judge has answered: the history model and the judge


def fit_on(data, years, shared=SHARED, use_judge=True):
    """Two sets of weights fitted on these years: one for nominees the judge has answered (history and
    judge), one for every other proposal (the seven shared inputs). With use_judge=False, or with too
    few judged nominees to fit on, every proposal uses the shared inputs."""
    train = [r for y in years for r in data[y]]
    judged = [r for r in train if r["xc"][8]] if use_judge else []
    if sum(r["y"] for r in judged) < 10:
        judged = []
    rest = [r for r in train if not r["xc"][8]] if judged else train
    return {"shared": shared,
            "rest": bm.fit_logistic([[r["xc"][i] for i in shared] for r in rest], [r["y"] for r in rest]),
            "judged": bm.fit_logistic([[r["xc"][i] for i in JUDGED] for r in judged], [r["y"] for r in judged]) if judged else None}


def score(fit, xc):
    """The combined probability for one proposal's inputs."""
    if fit["judged"] and xc[8]:
        return bm.predict(fit["judged"], [xc[i] for i in JUDGED])
    return bm.predict(fit["rest"], [xc[i] for i in fit["shared"]])


def flag_level(data, year):
    """The probability at which the tool says "against", chosen for best F1 on earlier years.
    Each earlier year is scored by a fit on the other earlier years, so the level is not
    chosen on scores the fit has already seen (except when there is only one earlier year)."""
    earlier = [y for y in sorted(data) if y < year]
    ps, ys = [], []
    for y in earlier:
        fit = fit_on(data, [u for u in earlier if u != y] or earlier)
        ps += [score(fit, r["xc"]) for r in data[y]]
        ys += [r["y"] for r in data[y]]
    return bm.best_f1_threshold(ps, ys)


_FITS = {}


def training_years(year):
    """The years a fit for `year` may learn from: every year with a saved Jev run before it."""
    return list(range(FIRST, year))


def fitted(year):
    """Weights and the "against" level for scoring `year`, from the years before it. Computed once."""
    if year not in _FITS:
        rows = bm.read_votes(VOTES)
        directors, worded = rule_tables()
        data = {y: year_data(rows, y, directors, worded) for y in training_years(year)}
        _FITS[year] = (fit_on(data, sorted(data)), flag_level(data, year))
    return _FITS[year]


def top(scores, ys, share):
    k = int(round(share * len(ys)))
    return sum(ys[i] for i in sorted(range(len(ys)), key=lambda i: -scores[i])[:k])


def interval(groups, value, draws=2000, seed=5):
    """95% interval for a number computed from proposals, by drawing whole meetings again and again.
    Votes at one meeting hang together, so meetings are drawn, not single proposals."""
    rng = random.Random(seed)
    keys = list(groups)
    out = []
    for _ in range(draws):
        sample = [r for k in rng.choices(keys, k=len(keys)) for r in groups[k]]
        v = value(sample)
        if v is not None:
            out.append(v)
    out.sort()
    return out[int(0.025 * len(out))], out[int(0.975 * len(out)) - 1]


def decide(r, p, level, need_support=False, country_facts=False):
    """(acts alone on "against", sent to a person) with the rules on top, as src/run.py does it.

    need_support: a probability above the level is not enough for the tool to act alone. The
    suggestion must also rest on something a person can check: a rule with its fact, or NBIM's
    own against-vote on the same item last time. Without that it goes to a person as a
    suggestion from the models."""
    rule_alone = (r["director"] and r["director"]["acts_alone"]) or r["worded"]
    rule_held = r["director"] and r["director"]["signals"] and not r["director"]["acts_alone"]
    strong = p >= level
    if need_support:
        says = bool(rule_alone or (strong and r["prev_same_item"] == 1 and not rule_held))
    else:
        says = bool(rule_alone or strong)
    return says, bool(not says and (p >= LOW or rule_held or (country_facts and r["country_fact"])))


def kind_of_flag(r):
    """What a suggestion "against" rests on."""
    jev = r["xc"][3] == 1.0
    if (r["director"] and r["director"]["signals"]) or r["worded"]:
        return "a rule with its fact"
    if r["prev_same_item"] == 1:
        return "NBIM opposed the same item last time" + (", and Jev says against" if jev else "")
    return "the models only: " + ("Jev says against, no earlier against-vote on the item" if jev else "neither Jev nor an earlier against-vote")


def main():
    rows = bm.read_votes(VOTES)
    directors, worded = rule_tables()
    years = [FIRST] + list(DEVELOP) + [FINAL]
    data = {y: year_data(rows, y, directors, worded) for y in years}
    turned = lambda r, col: (1 - float(r["comp"][col])) if r["mgmt_rec"] == "MOT" else float(r["comp"][col])
    systems = collections.OrderedDict()
    for y in years[1:]:
        fit, level = fit_on(data, [u for u in years if u < y]), flag_level(data, y)
        first = fit_on(data, [u for u in years if u < y], use_judge=False)
        for r in data[y]:
            r["p_new"], r["level"], r["p_first"] = score(fit, r["xc"]), level, score(first, r["xc"])
    systems["History model (main before)"] = lambda r: r["p"]
    systems["Marie's pipeline (Jev + second model)"] = lambda r: turned(r, "marie_score")
    systems["Combined model without the judge"] = lambda r: r["p_first"]
    systems["Combined model (now)"] = lambda r: r["p_new"]

    print("1. Ranking: how many against-votes are in the top of each system's list")
    print("   (AP = average precision. Every year is scored by fits on earlier years only.)")
    out = []
    for name, scorer in systems.items():
        for label, group in ((f"{DEVELOP[0]}-{DEVELOP[-1]}", DEVELOP), (str(FINAL), (FINAL,))):
            ap, t10, t25, t40, total = [], 0, 0, 0, 0
            for y in group:
                ys, sc = [r["y"] for r in data[y]], [scorer(r) for r in data[y]]
                ap.append(bm.average_precision(sc, ys))
                t10, t25, t40, total = t10 + top(sc, ys, .10), t25 + top(sc, ys, .25), t40 + top(sc, ys, .40), total + sum(ys)
            out.append([name, label, f"{sum(ap) / len(ap):.3f}", f"{t10}/{total}", f"{t25}/{total}", f"{t40}/{total}"])
    bm.table(["System", "Years", "AP", "In the top 10%", "In the top 25%", "In the top 40%"], out)

    print("\n2. Average precision year by year (Marie's notes: 2022 and 2023 are her cleanest years)")
    bm.table(["System"] + [str(y) for y in years[1:]],
             [[name] + [f"{bm.average_precision([scorer(r) for r in data[y]], [r['y'] for r in data[y]]):.3f}" for y in years[1:]]
              for name, scorer in systems.items()])

    print(f"\n3. When the combined model says 'against', what does the suggestion rest on? ({DEVELOP[0]}-{DEVELOP[-1]})")
    kinds = collections.defaultdict(lambda: [0, 0])
    for y in DEVELOP:
        for r in data[y]:
            if r["p_new"] >= r["level"]:
                kinds[kind_of_flag(r)][0] += 1
                kinds[kind_of_flag(r)][1] += r["y"]
    bm.table(["The suggestion rests on", "Suggestions", "Right", "Share"],
             [[k, n, hit, f"{hit / n:.0%}"] for k, (n, hit) in sorted(kinds.items(), key=lambda kv: -kv[1][1] / kv[1][0])])
    print("   So the tool acts on its own only with a rule and its fact, or NBIM's own against-vote on the item")
    print("   last time. A suggestion that rests on the models only goes to a person, marked as such.")

    print("\n4. As a decision rule, with the director and wording rules on top and the 5% level kept")
    out = []
    for label, group in ((f"{DEVELOP[0]}-{DEVELOP[-1]}", DEVELOP), (str(FINAL), (FINAL,))):
        for name, pick in (("History model + rules (main before)", lambda r: (r["p"], r["hist_thr"], False)),
                           ("Combined model, acts on every suggestion", lambda r: (r["p_new"], r["level"], False)),
                           ("Combined model, acts alone only with support", lambda r: (r["p_new"], r["level"], True)),
                           ("  + Japan and Korea facts bring in a person (now)", lambda r: (r["p_new"], r["level"], True, True))):
            n = against = says = right = person = seen = 0
            for y in group:
                for r in data[y]:
                    s, h = decide(r, *pick(r))
                    n, against, says, right = n + 1, against + r["y"], says + s, right + (s and r["y"])
                    person, seen = person + h, seen + (h and r["y"])
            out.append([label, name, says, right, says - right, f"{right / says:.0%}", f"{right / against:.0%}",
                        f"{person} ({person / n:.0%})", f"{right + seen}/{against} ({(right + seen) / against:.0%})"])
    bm.table(["Years", "System", "Acts alone on 'against'", "Right", "Wrong", "Precision", "Recall", "A person reads",
              "Against-votes suggested or seen"], out)

    print("\n4b. How sure are the 2026 numbers? (95% intervals, drawing whole meetings again; 2022-2025 next to them)")
    out = []
    for label, group in ((str(FINAL), (FINAL,)), (f"{DEVELOP[0]}-{DEVELOP[-1]}", DEVELOP)):
        by_meeting = collections.defaultdict(list)
        for y in group:
            for r in data[y]:
                r["now"] = decide(r, r["p_new"], r["level"], True, True)
                by_meeting[(r["company_id"], r["meeting_date"])].append(r)
        ratio = lambda num, den: (lambda rows: (sum(num(r) for r in rows) / sum(den(r) for r in rows)) if sum(den(r) for r in rows) else None)
        measures = [("right when the tool acts alone on 'against'", ratio(lambda r: r["now"][0] and r["y"], lambda r: r["now"][0])),
                    ("against-votes the tool finds alone", ratio(lambda r: r["now"][0] and r["y"], lambda r: r["y"])),
                    ("against-votes suggested or seen", ratio(lambda r: (r["now"][0] or r["now"][1]) and r["y"], lambda r: r["y"])),
                    ("share of proposals a person reads", ratio(lambda r: r["now"][1], lambda r: 1))]
        everything = [r for rows_ in by_meeting.values() for r in rows_]
        for name, f in measures:
            lo, hi = interval(by_meeting, f)
            out.append([label, name, f"{f(everything):.0%}", f"{lo:.0%} to {hi:.0%}"])
    bm.table(["Years", "Measure", "Value", "95% interval"], out)
    print("   With 66 against-votes in 2026 the intervals are wide. A few votes either way move every 2026 number.")

    print("\n4c. Is the combined probability honest? (2022-2026 together)")
    out = []
    pooled = [r for y in years[1:] for r in data[y]]
    for lo, hi in ((0, .02), (.02, .05), (.05, .10), (.10, .20), (.20, .40), (.40, .70), (.70, 1.01)):
        b = [r for r in pooled if lo <= r["p_new"] < hi]
        if b:
            out.append([f"{lo:.0%} to {min(hi, 1):.0%}", len(b), f"{sum(r['p_new'] for r in b) / len(b):.1%}", f"{sum(r['y'] for r in b) / len(b):.1%}"])
    bm.table(["The tool says", "Proposals", "Average stated", "Actually against the board"], out)

    print("\n5. What the combination learned (fitted on all years before 2026; positive = towards against)")
    fit = fit_on(data, years[:-1])
    print("   For every proposal except nominees the judge has answered:")
    for (name, text), wi in zip(INPUTS, fit["rest"][1:]):
        print(f"   {wi:+.2f}  {name:17} {text}")
    print("   For US director nominees the judge has answered:")
    for i, wi in zip(JUDGED, fit["judged"][1:]):
        print(f"   {wi:+.2f}  {INPUTS[i][0]:17} {INPUTS[i][1]}")
    print(f"   Level for saying against in {FINAL}: {data[FINAL][0]['level']:.3f}")

    print("\n6. What each part adds, 2022-2025 (average precision when one part is left out)")
    variants = [("everything", SHARED, True), ("without the judge", SHARED, False),
                ("without Jev", [0, 1, 4, 5, 6], True), ("without the second model", [0, 2, 3, 4, 5, 6], True),
                ("without main's rules", [0, 1, 2, 3], True), ("without the history model in the shared inputs", [1, 2, 3, 4, 5, 6], True)]
    out = []
    for name, shared, use_judge in variants:
        aps = []
        for y in DEVELOP:
            fit = fit_on(data, [u for u in years if u < y], shared, use_judge)
            aps.append(bm.average_precision([score(fit, r["xc"]) for r in data[y]], [r["y"] for r in data[y]]))
        out.append([name, f"{sum(aps) / len(aps):.3f}"])
    bm.table(["Inputs", f"AP {DEVELOP[0]}-{DEVELOP[-1]}"], out)


if __name__ == "__main__":
    main()
