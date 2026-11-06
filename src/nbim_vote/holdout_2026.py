"""Strict 2026 holdout: every fitted part learns from 2025 only, and nothing from 2026 is seen before evaluation.

    python -m nbim_vote.holdout_2026            # writes data/outputs/holdout_2026.md (no API calls, a few minutes)
    python -m nbim_vote.holdout_2026 --check    # also reruns with the 2026 answers shuffled: predictions must not move
    python -m nbim_vote.holdout_2026 --count    # how many Jev calls --jev would make (no calls)
    python -m nbim_vote.holdout_2026 --jev      # first asks Jev about 2026 with the frozen history (needs TYPESAFE_API_KEY;
                                                # inputs already in the cache cost nothing), then evaluates

How 2026 is kept out
  - Every 2026 proposal enters the pipeline with NBIM's vote, its rationale and the against-board flag blanked.
    The answers are kept apart and read only by evaluate(), after every recommendation is made.
  - History is frozen on 1 January 2026: NBIM's earlier votes, as history features, as Jev's context and as the
    combined score's record, come from meetings before 2026 only. No vote at an earlier 2026 meeting is used
    (the live pipeline would use them, since NBIM publishes each vote before the meeting).
  - Main's pay model is fitted on N-PX votes at 2025 meetings, and NBIM's "vote last season" input is hidden
    when that meeting was in 2026.

What learns from 2025 only (training rows are 2025 proposals; their inputs may look back at earlier votes)
  - triage model (gradient boosting) and its flag and review thresholds, the thresholds from 2025 scores given
    by models that did not see the company (five company folds);
  - the combined score (weights, review share), fitted on those company-held-out triage scores;
  - the review cut-off: a 2026 proposal is reviewed when its score is in the top review share of 2025's scores;
  - the director rules' trust monitor, the skip rule and the abstain/support signals (2025 votes only);
  - main's pay model.
The design itself (inputs, rules, settings) was made while looking at earlier runs that included 2026; see
the walk-forward report. This run removes 2026 from the fitting, not from the design history.

Three variants
  - without Jev: strict. Nothing in it has seen 2026.
  - with Jev, frozen history (--jev): Jev asked again about each 2026 proposal with the same input as v7, except
    that NBIM's earlier votes stop at 31 December 2025, and with the 2026 row's vote and rationale blanked.
    Saved in data/jev_runs/results_2026_history_v7_frozen.csv. Strict in data; the v7 input design was still
    chosen while looking at 2026.
  - with Jev's saved 2026 answers (v7): not strict. Jev's input then held NBIM's votes at earlier 2026 meetings.
"""

import argparse
import csv
import hashlib
import json
import random
from collections import defaultdict

import numpy as np
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.model_selection import GroupKFold

from nbim_vote import pay_model
from nbim_vote import triage_model as tm
from nbim_vote.against_board import Signals
from nbim_vote.company_facts import facts as company_facts
from nbim_vote.company_facts import safe_groups
from nbim_vote.director_rules import deciding_rule, rule_states
from nbim_vote.director_rules import needs_person as rule_needs_person
from nbim_vote.fit_combination import C
from nbim_vote.jev_mvp import (DATA, MODEL, RUNS, VOTE_OPTIONS, JevClient, build_history_index, build_questions, build_state,
                               candidate_rules, combination_features, guidelines_for, load_guideline_versions, load_votes,
                               mot_metrics, needs_person, recommend_vote, review_cutoff)

TRAIN_YEAR, TEST_YEAR = 2025, 2026
TRAIN_FROM, CUTOFF, TEST_TO = "2025-01-01", "2026-01-01", "2027-01-01"
HIDDEN = ("nbim_vote", "nbim_vote_raw", "against_board", "rationale_text", "rationale_section", "position_paper")
JEV_RUN = "history_v7"
FROZEN_RUN = RUNS / "results_2026_history_v7_frozen.csv"
LEVEL = "history"
OUT = DATA / "outputs" / "holdout_2026.md"


def read(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def split(rows):
    """(known rows before 2026, hidden 2026 rows, answers). The hidden rows carry no vote and no rationale."""
    known = [r for r in rows if r["meeting_date"] < CUTOFF]
    test = [r for r in rows if CUTOFF <= r["meeting_date"] < TEST_TO]
    answers = {(r["meeting_id"], r["item_no"]): r["nbim_vote"] for r in test}
    hidden = [{**r, **dict.fromkeys(HIDDEN, "")} for r in test]
    return known, hidden, answers


def jev_answers(year):
    """(jev_vote, p_mot) per proposal from a saved Jev run. Only Jev's own columns are read, never NBIM's vote."""
    return {(r["meeting_id"], r["item_no"]): (r["jev_vote"], float(r["p_mot"])) for r in read(RUNS / f"results_{year}_{JEV_RUN}.csv")}


def ask_jev_frozen(rows, count_only=False):
    """Ask Jev about every 2026 proposal in the v7 run with history frozen at 1 January 2026. Writes FROZEN_RUN.

    The input is built by build_state(), the same function as v7, from the hidden row (no vote, no rationale)
    and a history index of votes before 2026. Inputs already in the cache cost no call.
    count_only: only report how many inputs are not in the cache."""
    known, hidden, _ = split(rows)
    wanted = jev_answers(TEST_YEAR)
    hidden = [r for r in hidden if (r["meeting_id"], r["item_no"]) in wanted]
    index = build_history_index(known)
    versions = load_guideline_versions()
    asks = []
    for r in hidden:
        _, by_section = guidelines_for(r["meeting_date"], versions)
        rules = candidate_rules(r["proposal_type"], by_section)
        asks.append((r, build_state(r, rules, LEVEL, index), build_questions(rules, LEVEL, r["mgmt_rec"])))
    cache = RUNS / "cache.jsonl"
    cached = {json.loads(line)["key"] for line in cache.read_text(encoding="utf-8").splitlines()} if cache.exists() else set()
    key = lambda st, q: hashlib.sha256(json.dumps({"model": MODEL, "state": st, "questions": q}, sort_keys=True,
                                                 ensure_ascii=False).encode()).hexdigest()
    missing = sum(key(st, q) not in cached for _, st, q in asks)
    print(f"{len(asks)} proposals in 2026; {missing} need a new Jev call, {len(asks) - missing} are already cached.", flush=True)
    if count_only:
        return
    client = JevClient(cache)
    with open(FROZEN_RUN, "w", encoding="utf-8", newline="") as f:
        out = csv.writer(f)
        out.writerow(["meeting_id", "item_no", "jev_vote", "p_mot", "confidence"])
        for i, (r, st, q) in enumerate(asks, 1):
            vote = client.ask(st, q)["answers"]["vote"]
            out.writerow([r["meeting_id"], r["item_no"], vote["choice"], vote["probabilities"].get("MOT", 0.0), vote.get("confidence", "")])
            if i % 100 == 0:
                f.flush()
                print(f"  {i}/{len(asks)}", flush=True)
    print(f"Wrote {FROZEN_RUN.relative_to(DATA.parent)}", flush=True)


def triage(known, hidden):
    """Triage scores for 2025 (company-held-out) and 2026 (fitted on all of 2025), and the flag from 2025."""
    voted = [r for r in known if r["nbim_vote"] in VOTE_OPTIONS]
    rows = voted + hidden
    X = tm.build_features(rows)
    y = np.array([r["nbim_vote"] == "MOT" for r in voted] + [False] * len(hidden))
    train = np.array([r["meeting_date"] >= TRAIN_FROM for r in voted] + [False] * len(hidden))
    test = np.array([False] * len(voted) + [True] * len(hidden))
    held_out = np.zeros(len(rows))
    idx = np.where(train)[0]
    companies = [rows[i]["company_id"] for i in idx]
    for fit_i, score_i in GroupKFold(5).split(idx, groups=companies):
        fit_mask, score_mask = np.zeros(len(rows), bool), np.zeros(len(rows), bool)
        fit_mask[idx[fit_i]], score_mask[idx[score_i]] = True, True
        held_out[score_mask] = tm.fit_and_score(X, y, fit_mask, score_mask)
    low, flag = tm.choose_thresholds(held_out[train], y[train])
    scores = tm.fit_and_score(X, y, train, test)
    key = lambda r: (r["meeting_id"], r["item_no"])
    return ({key(rows[i]): float(held_out[i]) for i in idx}, {key(r): float(s) for r, s in zip(hidden, scores)}, flag)


def combination(rows_2025, p_jev, p_triage, index, use_jev):
    """The combined score fitted on 2025: (score function, review share, 2025 scores), as fit_combination.fit does it."""
    feats = [combination_features(r, p_jev[k] if use_jev else None, p_triage[k], index)
             for r in rows_2025 for k in [(r["meeting_id"], r["item_no"])]]
    y = np.array([r["nbim_vote"] == "MOT" for r in rows_2025])
    vec = DictVectorizer(sparse=False)
    X = vec.fit_transform(feats)
    held_out = np.zeros(len(y))
    for a, b in GroupKFold(5).split(X, y, [r["company_id"] for r in rows_2025]):
        held_out[b] = LogisticRegression(C=C, max_iter=3000).fit(X[a], y[a]).predict_proba(X[b])[:, 1]
    cut = max(t for t in np.unique(held_out) if y[held_out >= t].sum() >= tm.TARGET_RECALL * y.sum())
    model = LogisticRegression(C=C, max_iter=3000).fit(X, y)
    score = lambda f: float(model.predict_proba(vec.transform([f]))[0, 1])
    return score, float((held_out >= cut).mean()), [score(f) for f in feats]


def predict(rows, use_jev, frozen=False):
    """Recommendation and routing for every 2026 proposal in the Jev run, learned from 2025. Never reads a 2026 answer.
    frozen: Jev's 2026 answers from the frozen-history run instead of the saved v7 run."""
    known, hidden, _ = split(rows)
    by_key = {(r["meeting_id"], r["item_no"]): r for r in known + hidden}
    run_2025, run_2026 = jev_answers(TRAIN_YEAR), jev_answers(TEST_YEAR)
    if frozen:
        run_2026 = {(r["meeting_id"], r["item_no"]): (r["jev_vote"], float(r["p_mot"])) for r in read(FROZEN_RUN)}
    hidden = [r for r in hidden if (r["meeting_id"], r["item_no"]) in run_2026 and r["mgmt_rec"] in ("FOR", "MOT")]
    rows_2025 = [by_key[k] for k in run_2025 if by_key[k]["nbim_vote"] in VOTE_OPTIONS]
    train_2025 = [r for r in known if r["meeting_date"] >= TRAIN_FROM]

    held_out, p_model, flag = triage(known, hidden)
    index = build_history_index(known)  # votes before 2026 only: 2026 history is frozen at 1 January
    p_jev = {k: v[1] for k, v in run_2025.items()} | {k: v[1] for k, v in run_2026.items()}
    score, share, scores_2025 = combination(rows_2025, p_jev, held_out, index, use_jev)
    cutoff = review_cutoff(scores_2025, share)

    known_facts = company_facts()
    versions = load_guideline_versions()
    states = rule_states([r for r in train_2025 if r["proposal_type"] == "DIRECTOR_ELECTION"], known_facts,
                         guidelines_for, versions, extra=[r for r in hidden if r["proposal_type"] == "DIRECTOR_ELECTION"])
    signals_ab = Signals(train_2025, CUTOFF)
    skip = safe_groups(train_2025, known_facts, CUTOFF)
    strict_pay = lambda year: pay_model.score_window(TRAIN_FROM, CUTOFF, TEST_TO, freeze=True) if year == TEST_YEAR else {}
    pay = pay_model.PayModel(known_facts, scores=strict_pay)

    out = []
    for r in hidden:
        k = (r["meeting_id"], r["item_no"])
        m = p_model[k]
        call = run_2026[k][0] if use_jev else ("MOT" if m >= flag else "FOR")
        s = score(combination_features(r, run_2026[k][1] if use_jev else None, m, index))
        signals = states.get(k, [])
        pd = pay.decision(r)
        rule = deciding_rule(signals) is not None or bool(pd and pd["signal"] == "MOT")
        rule_review = rule_needs_person(signals) or bool(pd and pd["signal"] == "review")
        vote = recommend_vote(call, m, r["mgmt_rec"], flag, rule, signals_ab.support(r)[0], signals_ab.abstain(r)[0])
        safe = any(g in skip for g in known_facts.groups(r))
        reviewed = (s >= cutoff and not safe) or needs_person(vote, r["mgmt_rec"]) or rule_review
        out.append({"key": k, "board": r["mgmt_rec"], "vote": vote, "reviewed": reviewed, "score": s, "p_model": m})
    return out, {"flag": flag, "review_share": share, "cutoff": cutoff, "train": len(rows_2025)}


def evaluate(pred, answers):
    """The only place the 2026 answers are read."""
    keep = [p for p in pred if answers[p["key"]] in VOTE_OPTIONS]
    actual = [answers[p["key"]] == "MOT" for p in keep]
    m = mot_metrics([p["vote"] == "MOT" for p in keep], actual)
    board = mot_metrics([p["board"] == "MOT" for p in keep], actual)
    reviewed = [p["reviewed"] for p in keep]
    reached = sum(a and r for a, r in zip(actual, reviewed))
    return {"n": len(keep), "mot": sum(actual), "m": m, "board": board, "review": float(np.mean(reviewed)),
            "reached": reached, "ap": average_precision_score(actual, [p["score"] for p in keep]),
            "ap_triage": average_precision_score(actual, [p["p_model"] for p in keep])}


def pct(x):
    return f"{100 * x:.1f}%"


def shuffled_answers(rows):
    """A copy of the rows with the 2026 answers shuffled among the 2026 proposals (for --check)."""
    out = [dict(r) for r in rows]
    test = [r for r in out if CUTOFF <= r["meeting_date"] < TEST_TO]
    fields = {f: [r[f] for r in test] for f in HIDDEN}
    order = list(range(len(test)))
    random.Random(1).shuffle(order)
    for i, r in enumerate(test):
        for f in HIDDEN:
            r[f] = fields[f][order[i]]
    return out


NAMES = {(False, False): "Without Jev (strict)", (True, True): "With Jev, history frozen at 1 January 2026 (strict in data)",
         (True, False): "With Jev's saved v7 answers (not strict, see below)"}
SHORT = {(False, False): "without Jev", (True, True): "Jev frozen", (True, False): "Jev v7"}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--check", action="store_true", help="rerun with the 2026 answers shuffled; predictions must be identical")
    p.add_argument("--jev", action="store_true", help="ask Jev about 2026 with the frozen history first (API calls for inputs not cached)")
    p.add_argument("--count", action="store_true", help="only count how many Jev calls --jev would make")
    a = p.parse_args()
    rows = load_votes()
    if a.count or a.jev:
        ask_jev_frozen(rows, count_only=a.count)
        if a.count:
            return
    _, _, answers = split(rows)
    results, settings = {}, {}
    variants = [(False, False)] + ([(True, True)] if FROZEN_RUN.exists() else []) + [(True, False)]
    for v in variants:
        pred, settings[v] = predict(rows, *v)
        results[v] = evaluate(pred, answers)
        if a.check:
            again, _ = predict(shuffled_answers(rows), *v)
            same = [(x["vote"], x["reviewed"], round(x["score"], 12)) for x in pred] == \
                   [(x["vote"], x["reviewed"], round(x["score"], 12)) for x in again]
            print(f"{SHORT[v]}: predictions with shuffled 2026 answers {'identical' if same else 'DIFFER'}", flush=True)
            if not same:
                raise SystemExit("2026 answers reach the predictions: the holdout is not clean.")

    w = results[(False, False)]
    lines = ["# Strict 2026 holdout: learned from 2025 only", "",
             "Produced by `python -m nbim_vote.holdout_2026` (no API calls; `--jev` adds the frozen-history Jev run). Every "
             "fitted part learns from 2025 proposals; 2026 proposals enter with NBIM's vote and rationale blanked, and NBIM's "
             "history is frozen on 1 January 2026. The answers are read once, after every recommendation is made. See the "
             "module docstring for the details.", "",
             f"2026: {w['n']} proposals, {w['mot']} MOT. Trained on {settings[(False, False)]['train']} proposals from 2025.", "",
             "| Setup | Precision | Recall | F1 | Review | MOT reaching a person | AP combined | AP triage |",
             "|---|---:|---:|---:|---:|---:|---:|---:|",
             f"| Baseline: follow the board | {pct(w['board']['precision'])} | {pct(w['board']['recall'])} | **{pct(w['board']['f1'])}** | – | – | – | – |"]
    for v in variants:
        x = results[v]
        lines.append(f"| {NAMES[v]} | {pct(x['m']['precision'])} | {pct(x['m']['recall'])} | **{pct(x['m']['f1'])}** | "
                     f"**{pct(x['review'])}** | {x['reached']} ({pct(x['reached'] / x['mot'])}) | {x['ap']:.3f} | {x['ap_triage']:.3f} |")
    lines += ["", "Settings learned from 2025: " + "; ".join(
        f"{SHORT[v]}: triage flag {settings[v]['flag']:.3f}, review share {pct(settings[v]['review_share'])}" for v in variants), "",
        "## Read this", "",
        "- **Without Jev is strict.** No part of it has seen a 2026 vote, a 2026 rationale or a vote at an earlier 2026 meeting.",
        "- **With Jev, frozen history** asks Jev again with the same input as v7, except that NBIM's earlier votes stop at "
        "31 December 2025 (`--jev`). It sees no 2026 vote. The v7 input design was still chosen while looking at 2026, and "
        "Jev may have seen NBIM's public votes in its own training.",
        "- **With Jev's saved v7 answers is not strict.** Those answers were made with NBIM's votes at earlier 2026 "
        "meetings in Jev's input.",
        "- **Frozen history costs something.** A live system would know NBIM's votes at earlier 2026 meetings; here a "
        "December meeting sees nothing after 31 December 2025. The walk-forward report uses that live history.",
        "- **The design was not made blind.** Inputs, rules and settings were chosen in earlier runs that included 2026. "
        "This run keeps 2026 out of the fitting, not out of the design history.",
        "- **One year of training.** The walk-forward report fits on all earlier years; 2025 alone is less data.",
        f"- **2026 is small.** {w['mot']} MOT votes: each is about {100 / w['mot']:.1f} points of recall."]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[6:7 + len(variants) + 2]))
    print(f"Wrote {OUT.relative_to(DATA.parent)}")


if __name__ == "__main__":
    main()
