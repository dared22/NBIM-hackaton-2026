"""models.combined: NBIM voting decision support."""

import csv
from dataclasses import dataclass, field

from src import data as paths
from src.evidence import judge as jg
from src.models import history as bm
from src.models import scoring as logistic
from src.models.scoring import best_f1_threshold
from src.rules import board as br
from src.rules import policy

VOTES = paths.VOTES
COMPONENTS = paths.COMPONENTS
FIRST = 2021  # first year with a saved Jev run
LOW = bm.LOW  # below this the tool follows the board on its own


def load_components(year):
    """Marie's exported scores for one year, by (meeting, item). No votes in this file."""
    with open(COMPONENTS.format(year=year), encoding="utf-8", newline="") as f:
        return {(r["meeting_id"], r["item_no"]): r for r in csv.DictReader(f)}


@dataclass
class RunState:
    """Memoized inputs and fitted models, owned by one prediction invocation."""

    judges: dict = field(default_factory=jg.load_cache)
    facts: dict = field(default_factory=policy.load_facts)
    fits: dict = field(default_factory=dict)


def judge_answer(row, director, state=None):
    """The judge model's cached answer for a US director nominee ({"p", "rule", "reason"}), or None."""
    if not director:
        return None
    state = RunState() if state is None else state
    question = jg.director_state(row, director)
    return (
        state.judges.get(jg.state_key(f"{row['meeting_id']}-{row['item_no']}", question))
        if question
        else None
    )


def judge_probability(row, director, state):
    answer = judge_answer(row, director, state)
    return answer["p"] if answer else None


def inputs_for(row, comp, director, worded, judge_p=None):
    """The inputs for one proposal. `row` must carry the history model's probability in row["p"]."""
    board_against = row["mgmt_rec"] == "MOT"
    jev_p, second_p = float(comp["jev_p_mot"]), float(comp["triage_p"])
    if board_against:  # NBIM voting FOR is then the vote against the board
        jev_p, second_p = 1 - jev_p, 1 - second_p
        jev_against = comp["jev_vote"] == "FOR"
    else:
        jev_against = comp["jev_vote"] in ("MOT", "AVSTÅ")
    return [
        logistic.logit(row["p"], epsilon=1e-3),
        logistic.logit(second_p, epsilon=1e-3),
        logistic.logit(jev_p, epsilon=1e-3),
        float(jev_against),
        float(bool(director and director["signals"])),
        float(bool(director and director["acts_alone"])),
        float(bool(worded)),
        logistic.logit(judge_p, epsilon=1e-3) if judge_p is not None else 0.0,
        float(judge_p is not None),
    ]


def rule_tables():
    directors = {(r["meeting_id"], r["item_no"]): r for r in br.load_scored()}
    worded = {(r["meeting_id"], r["item_no"]): r for r in policy.load_scored() if r["rules"]}
    return directors, worded


def year_data(rows, year, directors, worded, state):
    """Every proposal of one year with its inputs, scored by a history model fitted on earlier years."""
    _, test, _, hist_thr = bm.run_year(rows, year)
    comp = load_components(year)
    out = []
    for r in test:
        k = (r["meeting_id"], r["item_no"])
        if k in comp:
            r["comp"], r["hist_thr"] = comp[k], hist_thr
            r["director"], r["worded"] = directors.get(k), worded.get(k)
            r["country_fact"] = policy.signal_for(r, state.facts)
            r["judge_p"] = judge_probability(r, r["director"], state)
            r["xc"] = inputs_for(r, comp[k], r["director"], r["worded"], r["judge_p"])
            out.append(r)
    return out


SHARED = list(range(7))  # the seven inputs every proposal has
JUDGED = [0, 7]  # for a nominee the judge has answered: the history model and the judge


def fit_on(data, years):
    """Two sets of weights fitted on these years: one for nominees the judge has answered (history and
    judge), one for every other proposal (the seven shared inputs). With too
    few judged nominees to fit on, every proposal uses the shared inputs."""
    train = [r for y in years for r in data[y]]
    judged = [r for r in train if r["xc"][8]]
    if sum(r["y"] for r in judged) < 10:
        judged = []
    rest = [r for r in train if not r["xc"][8]] if judged else train
    return {
        "shared": SHARED,
        "rest": logistic.fit_logistic(
            [[r["xc"][i] for i in SHARED] for r in rest], [r["y"] for r in rest]
        ),
        "judged": logistic.fit_logistic(
            [[r["xc"][i] for i in JUDGED] for r in judged], [r["y"] for r in judged]
        )
        if judged
        else None,
    }


def score(fit, xc):
    """The combined probability for one proposal's inputs."""
    if fit["judged"] and xc[8]:
        return logistic.predict(fit["judged"], [xc[i] for i in JUDGED])
    return logistic.predict(fit["rest"], [xc[i] for i in fit["shared"]])


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
    return best_f1_threshold(ps, ys)


def training_years(year):
    """The years a fit for `year` may learn from: every year with a saved Jev run before it."""
    return list(range(FIRST, year))


def fitted(year, state=None):
    """Weights and the "against" level for scoring `year`, from the years before it. Computed once."""
    state = RunState() if state is None else state
    if year not in state.fits:
        rows = bm.read_votes(VOTES)
        directors, worded = rule_tables()
        data = {y: year_data(rows, y, directors, worded, state) for y in training_years(year)}
        state.fits[year] = (fit_on(data, sorted(data)), flag_level(data, year))
    return state.fits[year]
