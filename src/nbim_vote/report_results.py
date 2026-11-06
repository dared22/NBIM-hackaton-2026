"""Write the results report, and optionally compare it with main's system.

Run from the repository root. Uses saved Jev answers only: no API calls.
    python -m nbim_vote.report_results                               # data/outputs/jev_results.md
    python -m nbim_vote.report_results --main-dir <checkout of main> # also the comparison files

Every test year is scored walk-forward, as the pipeline runs live:
  - the combination is fitted on all earlier years with a Jev run, pooled
  - the triage model trains on earlier years only
  - the review share ranks each proposal against the previous 12 months of scores (live)
  - groups NBIM never opposed in 100+ earlier proposals skip review
  - NBIM's director rules, applied in code to facts filed before the meeting (director_rules.py), recommend
    MOT once trusted; a rule that fires but is not trusted sends the proposal to a person
  - the vote follows the board, whichever way it recommends, unless there is a reason to depart
    (jev_mvp.recommend_vote, the same function the live pipeline uses)
Each year is also scored without any company facts (no EDINET, DART, SEC or proxy facts), to show what they add.

The comparison runs main's benchmark model (src/benchmark/model.py in the main checkout) in this
process, on the same data file and the same proposals, in two ways:
  - as main runs it: history frozen at the start of the test year
  - with live history: votes from earlier dates in the same year, as marie's pipeline uses
It reads main's full 2026 decisions from data/outputs/decisions_2026.csv in the checkout.

If the checkout has main's combined model (src/agent/combined_model.py: main's signals plus Jev and the
triage model exported from this branch), it is run in its own process inside the checkout, exactly as
main scores it (each year fitted on earlier years), three ways:
  - with the scores main committed (exported from this branch at commit a7d971a)
  - with the scores exported from this branch now (src/nbim_vote/export_components.py)
  - with this branch's final recommendation in place of Jev's vote (export_components.py --final-vote)
The checkout's files are never changed: the exports go to a temporary folder.
"""

import argparse
import csv
import importlib.util
import random
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from sklearn.metrics import average_precision_score

from nbim_vote.against_board import Signals, score_against
from nbim_vote.citations import Citer, nbim_section
from nbim_vote.company_facts import safe_groups
from nbim_vote.director_rules import TRUST_AFTER, deciding_rule, rule_states
from nbim_vote.director_rules import needs_person as rule_needs_person
from nbim_vote.company_facts import facts as company_facts
from nbim_vote.fit_combination import fit
from nbim_vote.explain import fact_reasons
from nbim_vote.jev_mvp import (DATA, RUNS, VOTES, build_history_index, cited_section, combined_score, guidelines_for, live_review,
                     load_guideline_versions, load_votes, needs_person, recommend_vote, review_cutoff)
from nbim_vote.triage_model import score_year

YEARS = (2021, 2022, 2023, 2024, 2025, 2026)  # years with saved Jev runs at history level
TEST_YEARS = YEARS[1:]                          # 2021 has no earlier Jev year to fit on
WITH, WITHOUT = "_v7", "_v5"                     # Jev runs with and without company facts in its input
CLEAN_HOLDOUT = RUNS / "results_2026_history_v2.csv"  # 2026 as first run, before any design change made after seeing it
OUT = DATA / "outputs"
SEEN = {
    2021: "run once, after the design was fixed", 2022: "run once, after the design was fixed",
    2023: "run once, after the design was fixed", 2024: "used to check the design",
    2025: "used to design the system", 2026: "holdout, run six times (v2-v7) while the design changed",
}
SHARES = (0.10, 0.25, 0.40)  # review budgets for the equal-effort comparison
DRAWS = 1000


def read(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def metrics(flagged, reviewed, score, actual):
    flagged, reviewed, actual = (np.asarray(x, bool) for x in (flagged, reviewed, actual))
    tp, fp, fn = int((flagged & actual).sum()), int((flagged & ~actual).sum()), int((~flagged & actual).sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    seen = flagged | reviewed
    return {
        "positives": int(actual.sum()), "precision": precision, "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        "hits": tp, "false_alarms": fp, "review_share": float(np.mean(seen)),
        "reached": int((seen & actual).sum()), "reached_share": float((seen & actual).sum() / actual.sum()),
        "never_seen": int((~seen & actual).sum()), "avg_precision": float(average_precision_score(actual, score)),
    }


def top(score, share):
    """The top share of proposals by score, ties broken by order (stable)."""
    k = int(round(share * len(score)))
    out = np.zeros(len(score), bool)
    out[np.argsort(-np.asarray(score), kind="stable")[:k]] = True
    return out


def rank_metrics(score, actual):
    """Threshold-free measures that do not depend on each system's own review share."""
    score, actual = np.asarray(score, float), np.asarray(actual, bool)
    k = int(actual.sum())
    out = {"avg_precision": float(average_precision_score(actual, score)),
           "r_precision": float((top(score, k / len(score)) & actual).sum() / k)}
    for s in SHARES:
        out[f"recall@{int(s * 100)}"] = float((top(score, s) & actual).sum() / k)
    return out


def pct(x):
    return f"{100 * x:.1f}%"


def table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" if i == 0 else "---:" for i in range(len(header))) + "|"]
    return out + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]


class Setup:
    """Everything computed once: votes, history, facts, triage scores with and without facts."""

    def __init__(self):
        self.rows = load_votes()
        self.by_key = {(r["meeting_id"], r["item_no"]): r for r in self.rows}
        self.index = build_history_index(self.rows)
        self.facts = company_facts()
        self.triage = {f: {y: score_year(self.rows, y, use_facts=f) for y in YEARS} for f in (True, False)}
        self.versions = load_guideline_versions()
        self.rule_states = rule_states(self.rows, self.facts, guidelines_for, self.versions)
        self.citers = {y: Citer(self.rows, f"{y}-01-01") for y in YEARS}  # text model trained before each year
        self._code = {}

    def code_section(self, year, key):
        """(section, source) the code citations give for MOT on this proposal (citations.py)."""
        if key not in self._code:
            r = self.by_key[key]
            _, by_section = guidelines_for(r["meeting_date"], self.versions)
            rule, source = self.citers[year].cite(r, "MOT", by_section, self.index, self.rule_states.get(key, []),
                                                  " ".join(fact_reasons(r, self.facts)[0]))
            self._code[key] = (cited_section(rule) if rule else "", source.split(" (")[0])
        return self._code[key]

    def scored(self, year, facts, combo, jev=True):
        results = read(RUNS / f"results_{year}_history{WITH if facts else WITHOUT}.csv")
        p_model = np.array([self.triage[facts][year].scores[r["meeting_id"], r["item_no"]] for r in results])
        scores = np.array([combined_score(self.by_key[r["meeting_id"], r["item_no"]], float(r["p_mot"]) if jev else None, m, self.index, combo)
                           for r, m in zip(results, p_model)])
        dates = [self.by_key[r["meeting_id"], r["item_no"]]["meeting_date"] for r in results]
        return results, p_model, scores, dates

    def walk_forward(self, year, facts, jev=True):
        """Recommendation and routing for one year, fitted on earlier years only. jev False: the pipeline without Jev."""
        combo = fit([y for y in YEARS if y < year], self.rows, tag=WITH if facts else WITHOUT, triage=self.triage[facts], use_jev=jev)
        results, p_model, scores, dates = self.scored(year, facts, combo, jev)
        _, _, prev_scores, prev_dates = self.scored(year - 1, facts, combo, jev)
        live = np.array(live_review(dates, scores, combo["review_share"], list(zip(prev_dates, prev_scores))))
        batch = scores >= review_cutoff(list(scores), combo["review_share"])
        flag = combo["model_flag"]
        signals = [self.rule_states.get((r["meeting_id"], r["item_no"]), []) if facts else [] for r in results]
        rule = np.array([deciding_rule(x) is not None for x in signals])
        rule_review = np.array([rule_needs_person(x) for x in signals])
        # Without Jev, the triage model's own call stands in for Jev's vote (jev_mvp.model_answers).
        calls = [r["jev_vote"] if jev else ("MOT" if m >= flag else "FOR") for r, m in zip(results, p_model)]
        # Where "MOT" and "against the board" differ: abstention markets and proposals NBIM supports against the board.
        signals_ab = Signals(self.rows, f"{year}-01-01")
        rows_ = [self.by_key[r["meeting_id"], r["item_no"]] for r in results]
        support = [signals_ab.support(r)[0] for r in rows_]
        abstain = [signals_ab.abstain(r)[0] for r in rows_]
        votes = np.array([recommend_vote(c, m, r["mgmt_rec"], flag, ru, su, ab)
                          for c, r, m, ru, su, ab in zip(calls, results, p_model, rule, support, abstain)])
        votes_no_rule = np.array([recommend_vote(c, m, r["mgmt_rec"], flag) for c, r, m in zip(calls, results, p_model)])
        person = np.array([needs_person(v, r["mgmt_rec"]) for v, r in zip(votes, results)]) | rule_review
        person_no_rule = np.array([needs_person(v, r["mgmt_rec"]) for v, r in zip(votes_no_rule, results)])
        skip_groups = safe_groups(self.rows, self.facts, f"{year}-01-01") if facts else set()
        safe = np.array([any(g in skip_groups for g in self.facts.groups(self.by_key[r["meeting_id"], r["item_no"]])) for r in results])
        actual = np.array([r["nbim_vote"] == "MOT" for r in results])
        board = np.array([r["mgmt_rec"] for r in results])
        return {"results": results, "scores": scores, "p_model": p_model, "actual": actual, "combo": combo,
                "flag_against": votes != board, "scores_against": np.array([score_against(x, b) for x, b in zip(scores, board)]),
                "triage_against": np.array([score_against(x, b) for x, b in zip(p_model, board)]),
                "skip_groups": skip_groups, "votes": votes, "flagged": votes == "MOT", "flagged_no_rule": votes_no_rule == "MOT",
                "person": person, "person_no_rule": person_no_rule, "rule_flag": rule, "rule_review": rule_review, "signals": signals, "safe": safe, "live": live,
                "batch": batch, "reviewed": (live & ~safe) | person}


def row_metrics(w, reviewed=None, flagged=None):
    return metrics(w["flagged"] if flagged is None else flagged, w["reviewed"] if reviewed is None else reviewed, w["scores"], w["actual"])


def clean_holdout():
    """2026 as first run (v2), before the later design changes. Its own recommendation and routing, as saved."""
    rows = read(CLEAN_HOLDOUT)
    actual = np.array([r["nbim_vote"] == "MOT" for r in rows])
    flagged = np.array([r["vote"] == "MOT" for r in rows])
    reviewed = np.array([r["route"] == "human_review" for r in rows])
    board = np.array([r["mgmt_rec"] == "MOT" for r in rows])
    return metrics(flagged, reviewed, [float(r["p_model"]) for r in rows], actual), metrics(board, board, board, actual), len(rows)


def my_report(s, runs, runs_nojev):
    lines = ["# Jev pipeline: walk-forward results with company facts", "",
             "Produced by `python -m nbim_vote.report_results`, from saved Jev answers (no API calls).", "",
             "## Read this first", "",
             "- **2026 is not a clean holdout.** It was run six times (v2-v7) while the design changed. The first run, before any "
             "change made after seeing it, is the honest 2026 number (table below). Its F1 is close to the tuned run; "
             "its review share is much higher. The cut in review effort was found while looking at 2026.",
             "- 2024 and 2025 were used to design and check the system. 2022 and 2023 were each run once, after the design was fixed, "
             "and are the cleanest years.",
             "- **Citations are scored optimistically for 2022-2024.** The map from proposal type to candidate guideline "
             "sections (`TYPE_TO_SECTIONS`) was built from the sections NBIM cited at meetings before 2025, so those years' "
             "own citations helped decide which rules Jev may name.",
             "- **Jev may have seen NBIM's votes in training.** NBIM's votes and rationales are public since 2013 and Jev's "
             "training cutoff is unknown. Jev alone scores about the same in every year (F1 40-47%), including 2026, so there is no "
             "sign of a large effect, but it cannot be ruled out for the earlier years.",
             "- **The board-MOT rule was chosen on 2021-2025** (the share of board-MOT proposals where the recommendation "
             "matches NBIM's vote), which overlaps the test years 2022-2025. It touches 14-27 proposals a year.",
             "- **Confidence** is the combined score's rank against the previous 12 months, not Jev's own confidence. "
             "It decides which proposals a person sees.", "",
             "## How each year is scored", "",
             "- **Walk-forward.** The combination (weights, review share, model flag) is fitted on all earlier years with a Jev run, "
             "pooled. The triage model trains on earlier years only.",
             "- **Live review share.** Each proposal is ranked against the previous 12 months of scores, starting from last year's run, "
             "as a live system would. Nothing from later in the year is used.",
             "- **Recommendation:** MOT when Jev votes MOT and the triage model is at or above the flag, or when one of NBIM's "
             "director rules, applied in code to facts filed before the meeting, fires with verified facts and is trusted. "
             "AVSTÅ when Jev's top choice is "
             "AVSTÅ. Otherwise the board's recommendation, except that a board MOT becomes FOR when Jev and the triage model both "
             "say NBIM would not oppose. Every MOT, AVSTÅ and departure from the board goes to a person.",
             "- **Skip rule:** a group (proposal type, or nominee role in Japan, Korea or the US) skips review when NBIM opposed none of "
             "at least 100 such proposals in earlier years.",
             "- **Company facts**, all from documents filed before the meeting: Japan (EDINET annual reports: nominee role, board "
             "independence), US (main's reading of each proxy: nominee role, independence, chair, attendance; last year's vote results "
             "from SEC 8-K item 5.07; CEO pay), Korea (OpenDART: board composition, CEO also chair; nominee role from the ballot). "
             "They go to the triage model and into Jev's input.",
             "- **Target:** NBIM voted MOT. Abstentions count as not MOT.", "",
             "## Every test year", ""]
    out = []
    for year in TEST_YEARS:
        w = runs[(year, True)]
        m = row_metrics(w)
        board = np.array([r["mgmt_rec"] == "MOT" for r in w["results"]])
        jev = np.array([r["jev_vote"] == "MOT" for r in w["results"]])
        b, j = metrics(board, board, board, w["actual"]), metrics(jev, jev, jev, w["actual"])
        right = [r for r, f, a in zip(w["results"], w["flagged"], w["actual"]) if f and a and r["rationale_section"].startswith("GVG")]
        cited = sum(r["rationale_section"] == "GVG " + (r["mot_section"] or r["cited_section"]) for r in right)
        code = sum(s.code_section(year, (r["meeting_id"], r["item_no"]))[0] == nbim_section(r["rationale_section"]) for r in right)
        label = f"{year} (tuned on it)" if year == 2026 else str(year)
        out.append([label, f"{min(w['combo']['fitted_on'])}-{max(w['combo']['fitted_on'])}", len(w["results"]), m["positives"],
                    pct(b["f1"]), pct(j["f1"]), pct(m["precision"]), pct(m["recall"]), f"**{pct(m['f1'])}**",
                    f"**{pct(m['review_share'])}**", f"{m['reached']} ({pct(m['reached_share'])})", f"{m['avg_precision']:.3f}", f"{code} / {cited} of {len(right)}"])
    if CLEAN_HOLDOUT.exists():
        c, b, n = clean_holdout()
        out.append(["**2026 clean (v2, as first run)**", "2025 only", n, c["positives"], pct(b["f1"]), "–", pct(c["precision"]), pct(c["recall"]),
                    f"**{pct(c['f1'])}**", f"**{pct(c['review_share'])}**", f"{c['reached']} ({pct(c['reached_share'])})", "–", "–"])
    lines += table(["Year", "Fitted on", "Proposals", "MOT", "Board F1", "Jev alone F1", "Precision", "Recall", "F1", "Review",
                    "MOT reaching a person", "AP combined", "Right section: code / Jev"], out)
    lines += ["", "2021 is not a test year: there is no earlier Jev year to fit on. 2019 and 2020 have no runs: the triage model needs two "
              "earlier years of votes. The clean 2026 row is the pipeline as it stood then (Jev + triage model, routing fitted on 2025, "
              "no company facts, no live review share), read from `results_2026_history_v2.csv`. "
              "Right section: correct MOT recommendations where the guideline section named matches the one NBIM cited, "
              "with citations from code (the default) and from Jev.", "",
              "## What each piece adds", "",
              "Average over the test years. Each row adds one piece to the row above.", ""]
    steps = []
    for name, fn in (
        ("No company facts, ranked within the year", lambda y: row_metrics(runs[(y, False)], runs[(y, False)]["batch"] | runs[(y, False)]["person"])),
        ("+ live review share (previous 12 months)", lambda y: row_metrics(runs[(y, False)])),
        ("+ company facts in the model and in Jev's input", lambda y: row_metrics(runs[(y, True)], runs[(y, True)]["live"] | runs[(y, True)]["person_no_rule"], runs[(y, True)]["flagged_no_rule"])),
        ("+ NBIM's director rules in code, with trust monitor", lambda y: row_metrics(runs[(y, True)], runs[(y, True)]["live"] | runs[(y, True)]["person"])),
        ("+ skip rule (the full system)", lambda y: row_metrics(runs[(y, True)])),
    ):
        ms = [fn(y) for y in TEST_YEARS]
        mean = lambda k: sum(m[k] for m in ms) / len(ms)
        steps.append([name, f"**{pct(mean('f1'))}**", pct(mean("precision")), pct(mean("recall")), f"**{pct(mean('review_share'))}**", pct(mean("reached_share"))])
    lines += table(["Setup", "F1", "Precision", "Recall", "Review", "MOT reaching a person"], steps)

    lines += ["", "## With and without Jev", "",
              "Without Jev (`--no-jev`), the triage model's own call replaces Jev's vote, the combination is refitted without Jev's "
              "feature on the same earlier years, and the director rules, skip rule and code citations work as before. "
              "Everything else is the same walk-forward setup.", ""]
    out, sums = [], defaultdict(list)
    for year in TEST_YEARS:
        for name, w in (("with Jev", runs[(year, True)]), ("without Jev", runs_nojev[year])):
            m = row_metrics(w)
            for k in ("f1", "precision", "recall", "review_share", "reached_share", "avg_precision"):
                sums[(name, k)].append(m[k])
            out.append([year, name, pct(m["precision"]), pct(m["recall"]), f"**{pct(m['f1'])}**", f"**{pct(m['review_share'])}**",
                        f"{m['reached']} ({pct(m['reached_share'])})", f"{m['avg_precision']:.3f}"])
    for name in ("with Jev", "without Jev"):
        mean = lambda k: sum(sums[(name, k)]) / len(sums[(name, k)])
        out.append(["**Average**", name, pct(mean("precision")), pct(mean("recall")), f"**{pct(mean('f1'))}**",
                    f"**{pct(mean('review_share'))}**", pct(mean("reached_share")), f"{mean('avg_precision'):.3f}"])
    lines += table(["Year", "Pipeline", "Precision", "Recall", "F1", "Review", "MOT reaching a person", "AP combined"], out)

    lines += ["", "## Citations: code or Jev", "",
              "On every proposal NBIM voted MOT on with a guideline section in its rationale, whether or not it was recommended: "
              "does the citation name NBIM's section? Jev's is the MOT rule it rated highest; code's comes from `src/nbim_vote/citations.py` "
              "(rule in code, then NBIM's earlier reason for the same item, then for the same company and proposal type, then a "
              "text model trained on earlier years only). Both see only earlier meetings. Jev's candidate rules were mapped from "
              "NBIM's citations before 2025, so Jev's 2022-2024 numbers are optimistic. The order of the code sources was set "
              "before this comparison and checked on 2020-2021 only.", ""]
    out, by_source = [], defaultdict(lambda: [0, 0])
    total = [0, 0, 0]
    for year in TEST_YEARS:
        cases = [r for r in runs[(year, True)]["results"] if r["nbim_vote"] == "MOT" and nbim_section(r["rationale_section"])]
        jev_right = sum(r["mot_section"] == nbim_section(r["rationale_section"]) for r in cases)
        code_right = 0
        for r in cases:
            section, source = s.code_section(year, (r["meeting_id"], r["item_no"]))
            ok = section == nbim_section(r["rationale_section"])
            code_right += ok
            by_source[source or "none"][0] += 1
            by_source[source or "none"][1] += ok
        total = [total[0] + len(cases), total[1] + jev_right, total[2] + code_right]
        out.append([year, len(cases), f"{jev_right} ({pct(jev_right / len(cases))})", f"{code_right} ({pct(code_right / len(cases))})"])
    out.append(["**All**", total[0], f"**{total[1]} ({pct(total[1] / total[0])})**", f"**{total[2]} ({pct(total[2] / total[0])})**"])
    lines += table(["Year", "NBIM MOT with a section", "Jev names it", "Code names it"], out)
    lines += ["", "Code citations by source, all test years:", ""]
    lines += table(["Source", "Cases", "Names NBIM's section"],
                   [[k, n, f"{ok} ({pct(ok / n)})"] for k, (n, ok) in sorted(by_source.items(), key=lambda kv: -kv[1][0])])

    lines += ["", "## When the board recommends MOT", "",
              "Mostly shareholder proposals. The earlier rule voted FOR unless Jev and the model both said MOT, which went against "
              "the board without a reason. The vote now follows the board unless Jev and the model both say NBIM would support "
              "the proposal.", ""]
    out = []
    flag_by_year = {y: runs[(y, True)]["combo"]["model_flag"] for y in TEST_YEARS}
    for year in TEST_YEARS:
        w = runs[(year, True)]
        idx = [i for i, r in enumerate(w["results"]) if r["mgmt_rec"] == "MOT"]
        old = ["MOT" if (w["results"][i]["jev_vote"] == "MOT" and w["p_model"][i] >= flag_by_year[year]) or w["rule_flag"][i] else "FOR" for i in idx]
        nbim = [w["results"][i]["nbim_vote"] for i in idx]
        out.append([year, len(idx), Counter(nbim)["MOT"], sum(o == n for o, n in zip(old, nbim)),
                    sum(w["votes"][i] == n for i, n in zip(idx, nbim)), sum(n == "MOT" for n in nbim)])
    lines += table(["Year", "Board MOT", "NBIM MOT", "Matches NBIM, earlier rule", "Matches NBIM, now", "Matches NBIM, always follow the board"], out)

    lines += ["", "## Abstentions (AVSTÅ)", "",
              "AVSTÅ is recommended when Jev's top choice is AVSTÅ, and always goes to a person. NBIM abstains on about 0.5% of proposals.", ""]
    out = []
    for year in TEST_YEARS:
        w = runs[(year, True)]
        rec = w["votes"] == "AVSTÅ"
        nbim = np.array([r["nbim_vote"] == "AVSTÅ" for r in w["results"]])
        out.append([year, int(rec.sum()), int((rec & nbim).sum()), int(nbim.sum())])
    lines += table(["Year", "Recommended AVSTÅ", "NBIM abstained on those", "NBIM abstentions in all"], out)

    lines += ["", "## Skip rule", "", "Groups that skip review, learned from earlier years only:", ""]
    out = []
    for year in TEST_YEARS:
        w = runs[(year, True)]
        would = w["live"] & w["safe"] & ~w["person"]
        out.append([year, "; ".join(sorted(w["skip_groups"])) or "none yet", int(would.sum()), int((would & w["actual"]).sum())])
    lines += table(["Year", "Groups", "Proposals skipped", "MOT among them"], out)

    lines += ["", "## NBIM's director rules, applied in code", "",
              "Each rule is NBIM's own (guideline number), applied to facts filed before the meeting: US facts from main's AI "
              "reading of the proxy (a quote checked against the text), Japanese facts from the EDINET annual report. A rule "
              f"decides MOT on its own only when NBIM followed it at the last {TRUST_AFTER} earlier meetings where it fired and its "
              "facts are verified; otherwise the proposal goes to a person with the fact. The trust rule is main's, untuned. "
              "The rules were chosen from the guideline text and main's list, which main says was made after looking at all years.", ""]
    out = []
    for year in TEST_YEARS:
        w = runs[(year, True)]
        per = defaultdict(lambda: [0, 0, 0, 0])
        for sig, a in zip(w["signals"], w["actual"]):
            decided = deciding_rule(sig)
            for rule, _, _, source, _, _ in sig:
                x = per[(rule, source)]
                x[0] += 1
                x[1] += bool(a)
                x[2] += decided == rule
                x[3] += decided == rule and bool(a)
        for (rule, source), (n, mot, dec, dec_mot) in sorted(per.items()):
            out.append([year, f"{rule} ({source})", n, mot, dec, f"{dec_mot}/{dec}" if dec else "–", n - dec])
    lines += table(["Year", "Rule", "Fired", "NBIM MOT", "Decided alone", "MOT when decided", "Sent to a person"], out)

    lines += ["", "## Coverage of the company facts", ""]
    cov = defaultdict(Counter)
    for year in TEST_YEARS:
        for r in runs[(year, True)]["results"]:
            row = s.by_key[r["meeting_id"], r["item_no"]]
            for kind, value in (("Japan director", s.facts.japan.for_row(row)), ("US director", s.facts.us_director(row)),
                                ("US pay vote", s.facts.us_pay(row)), ("Korea director", s.facts.korea_director(row))):
                if value is not None:
                    cov[kind]["proposals"] += 1
                    cov[kind]["found"] += bool(value.get("found"))
                    cov[kind]["mot"] += r["nbim_vote"] == "MOT"
    lines += table(["Proposals", "In test years", "With facts", "NBIM MOT"],
                   [[k, c["proposals"], f"{c['found']} ({pct(c['found'] / c['proposals'])})", c["mot"]] for k, c in cov.items()])
    resistance = sorted(OUT.glob("resistance_*.md"))
    lines += ["", "## Resistance test", "",
              "An instruction is added to what the agent reads; see " + (", ".join(f"`{p.name}`" for p in resistance) or "(not run yet)")
              + " for the full tables. Run with `python -m nbim_vote.jev_mvp --year 2025 --n 100 --level history --resistance --enrich`.", ""]
    lines += ["## What to keep in mind", "",
              "- How each year was used: " + "; ".join(f"{y} {t}" for y, t in SEEN.items()) + ".",
              "- EDINET only keeps AGM vote results from mid-2024, so Japanese last-year support reaches 2025-26 only. US vote results "
              "go back to 2018.",
              "- US nominee facts come from main's AI reading of each proxy; their accuracy is main's, and is checked there.",
              "- Each MOT vote is 1-2 percentage points of recall, so small differences between years are noise.", ""]
    return lines


# ---------------------------------------------------------------- comparison with main

def load_main_model(main_dir):
    path = Path(main_dir) / "src" / "benchmark" / "model.py"
    spec = importlib.util.spec_from_file_location("main_benchmark_model", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main_history_model(mod, rows, test_year, live):
    """main's run_year, with the history either frozen at the start of the year (as main runs it) or live.

    Live adds each date's outcomes to the history after that date, so a proposal sees earlier meetings in
    its own year, never its own date. That is the information marie's pipeline has.
    """
    year = lambda r: int(r["meeting_date"][:4])
    frozen = lambda y: None if live else f"{y}-01-01"
    train = [r.copy() for r in rows if year(r) < test_year]
    test = [r.copy() for r in rows if year(r) == test_year]
    mod.add_history_features(train + test, frozen(test_year))
    fit_part = [r for r in train if year(r) < test_year - 1]
    val_part = [r.copy() for r in train if year(r) == test_year - 1]
    mod.add_history_features(fit_part + val_part, frozen(test_year - 1))
    w_val = mod.fit_logistic([r["x"] for r in fit_part], [r["y"] for r in fit_part])
    threshold = mod.best_f1_threshold([mod.predict(w_val, r["x"]) for r in val_part], [r["y"] for r in val_part])
    w = mod.fit_logistic([r["x"] for r in train], [r["y"] for r in train])
    out = {}
    for r in test:
        p = mod.predict(w, r["x"])
        out[r["meeting_id"], r["item_no"]] = (p, p >= threshold, mod.LOW <= p < threshold)
    return out


# Runs in main's checkout, in its own process (main's modules share names with this branch's).
# It repeats combined_model.main(): every year is scored by a fit on the years before it.
MAIN_COMBINED_SCRIPT = """
import csv, sys
sys.path[:0] = ["src", "src/agent"]
import combined_model as cm
if len(sys.argv) > 2:
    cm.COMPONENTS = sys.argv[2]  # another export of this branch's scores, as a pattern with {year}
rows = cm.bm.read_votes(cm.VOTES)
directors, worded = cm.rule_tables()
years = [cm.FIRST, *cm.DEVELOP, cm.FINAL]
data = {y: cm.year_data(rows, y, directors, worded) for y in years}
with open(sys.argv[1], "w", newline="", encoding="utf-8") as f:
    out = csv.writer(f)
    out.writerow(["meeting_id", "item_no", "year", "p", "says", "person"])
    for y in years[1:]:
        weights, level = cm.fit_on(data, [u for u in years if u < y]), cm.flag_level(data, y)
        for r in data[y]:
            p = cm.bm.predict(weights, r["xc"])
            says, person = cm.decide(r, p, level)
            out.writerow([r["meeting_id"], r["item_no"], y, p, int(says), int(person)])
"""


def main_combined(main_dir, components=None):
    """{(meeting, item): (p, says against, sent to a person)} from main's combined model, or None if main has none.
    components: a folder of exported component files to use instead of the ones committed on main."""
    if not (Path(main_dir) / "src" / "agent" / "combined_model.py").exists():
        return None
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "combined.csv"
        args = [str(out)] + ([str(Path(components) / "components_{year}.csv")] if components else [])
        subprocess.run([sys.executable, "-c", MAIN_COMBINED_SCRIPT, *args], cwd=main_dir, check=True,
                       env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
        return {(r["meeting_id"], r["item_no"]): (float(r["p"]), r["says"] == "1", r["person"] == "1") for r in read(out)}


def check_against_committed(main_dir, frozen_2026, votes):
    """main's committed 2026 file should match our in-process run of it. Returns the largest difference."""
    path = Path(main_dir) / "src" / "benchmark" / "prediksjoner_2026.csv"
    if not path.exists():
        return None
    ours = defaultdict(list)
    for (mid, item), (p, _, _) in frozen_2026.items():
        r = votes[mid, item]
        ours[(r["meeting_date"], r["company"], r["proposal_text"])].append(p)
    diffs = [min(abs(float(t["probability_against"]) - p) for p in ours[(t["meeting_date"], t["company"], t["proposal_text"])])
             for t in read(path) if ours.get((t["meeting_date"], t["company"], t["proposal_text"]))]
    return max(diffs) if diffs else None


def bootstrap(per_year, years, a, b, target, measure, seed=42):
    """95% interval for system a minus system b, resampling meetings within each year."""
    rng = random.Random(seed)
    groups = []
    for y in years:
        meetings = defaultdict(list)
        for i, mid in enumerate(per_year[y]["meeting"]):
            meetings[mid].append(i)
        groups.append((y, list(meetings.values())))
    diffs = []
    for _ in range(DRAWS):
        sa, sb, act = [], [], []
        for y, ms in groups:
            idx = [i for m in rng.choices(ms, k=len(ms)) for i in m]
            d = per_year[y]
            sa.append(d["scores"][target][a][idx]), sb.append(d["scores"][target][b][idx]), act.append(d["targets"][target][idx])
        if measure == "avg_precision":
            # Pooled ranking would mix years with different base rates, so average the years.
            va = np.mean([average_precision_score(t, s) for s, t in zip(sa, act)])
            vb = np.mean([average_precision_score(t, s) for s, t in zip(sb, act)])
        else:
            share = float(measure.split("@")[1]) / 100
            va = np.mean([(top(s, share) & t).sum() / t.sum() for s, t in zip(sa, act)])
            vb = np.mean([(top(s, share) & t).sum() / t.sum() for s, t in zip(sb, act)])
        diffs.append(va - vb)
    diffs.sort()
    return diffs[int(0.025 * DRAWS)], diffs[int(0.975 * DRAWS)]


MARIE, MARIE_TRIAGE = "marie: Jev pipeline + facts", "marie: triage model only (no Jev)"
MARIE_NOJEV = "marie: pipeline without Jev"
MAIN_FROZEN, MAIN_LIVE, MAIN_FULL = "main: history model, as committed", "main: history model, live history", "main: full system (2026 only)"
MAIN_COMBINED = "main: combined model, marie as committed on main (a7d971a)"
MAIN_COMBINED_NOW = "main: combined model, current marie"
MAIN_COMBINED_FINAL = "main: combined model, marie's final vote"
COMBINED = (MAIN_COMBINED, MAIN_COMBINED_NOW, MAIN_COMBINED_FINAL)
BOARD = "Follow the board"
RANKED = (MARIE, MARIE_NOJEV, MARIE_TRIAGE, MAIN_FROZEN, MAIN_LIVE)
TARGETS = ("NBIM voted MOT", "against the board")


def compare(s, runs, main_dir, runs_nojev):
    mod = load_main_model(main_dir)
    combined = {}
    if main_combined(main_dir) is not None:
        from nbim_vote.export_components import export  # Imported here because it imports this file.
        with tempfile.TemporaryDirectory() as tmp:
            export(Path(tmp) / "now", setup=s)
            export(Path(tmp) / "final", final_vote=True, setup=s)
            combined = {MAIN_COMBINED: main_combined(main_dir), MAIN_COMBINED_NOW: main_combined(main_dir, Path(tmp) / "now"),
                        MAIN_COMBINED_FINAL: main_combined(main_dir, Path(tmp) / "final")}
    ranked = RANKED + tuple(combined)
    main_rows = mod.read_votes(str(VOTES))
    votes = s.by_key
    per_year, csv_rows = {}, []
    frozen_2026 = None
    for year in TEST_YEARS:
        w = runs[(year, True)]
        frozen = main_history_model(mod, main_rows, year, live=False)
        live = main_history_model(mod, main_rows, year, live=True)
        if year == 2026:
            frozen_2026 = frozen
        keys = [(r["meeting_id"], r["item_no"]) for r in w["results"]]
        idx = np.array([i for i, k in enumerate(keys) if k in frozen and all(k in c for c in combined.values())])  # every system scores these
        results = [w["results"][i] for i in idx]
        keys = [keys[i] for i in idx]
        targets = {"NBIM voted MOT": w["actual"][idx],
                   "against the board": np.array([votes[k]["against_board"] in ("1", "1.0") for k in keys])}
        board = np.array([r["mgmt_rec"] == "MOT" for r in results])
        none = np.zeros(len(results), bool)
        systems = {
            MARIE: (w["flagged"][idx], w["reviewed"][idx], w["scores"][idx]),
            MARIE_NOJEV: (runs_nojev[year]["flagged"][idx], runs_nojev[year]["reviewed"][idx], runs_nojev[year]["scores"][idx]),
            MARIE_TRIAGE: (w["p_model"][idx] >= w["combo"]["model_flag"], none, w["p_model"][idx]),
            MAIN_FROZEN: tuple(np.array([frozen[k][j] for k in keys]) for j in (1, 2, 0)),
            MAIN_LIVE: tuple(np.array([live[k][j] for k in keys]) for j in (1, 2, 0)),
            BOARD: (board, none, board.astype(float)),
        }
        for name, scores in combined.items():
            systems[name] = tuple(np.array([scores[k][j] for k in keys]) for j in (1, 2, 0))
        # marie predicts NBIM's MOT votes. For "against the board", her recommendation counts when it departs from the
        # board (MOT, AVSTÅ, or FOR on a board MOT), and her score is turned around where the board recommends MOT,
        # as main's combined model does with her scores.
        nj = runs_nojev[year]
        against = {MARIE: (w["flag_against"][idx], w["scores_against"][idx]),
                   MARIE_NOJEV: (nj["flag_against"][idx], nj["scores_against"][idx]),
                   MARIE_TRIAGE: (np.where(board, w["p_model"][idx] < w["combo"]["model_flag"], w["p_model"][idx] >= w["combo"]["model_flag"]),
                                  w["triage_against"][idx])}
        if year == 2026:
            dec = {r["key"]: r for r in read(Path(main_dir) / "data" / "outputs" / "decisions_2026.csv") if r["dataset"] == "NBIM votes, all proposal types"}
            d = [dec.get(f"{mid}-{item}") for mid, item in keys]
            if all(d):
                systems[MAIN_FULL] = (np.array([x["suggested_vote"] in ("MOT", "AVSTÅ") for x in d]),
                                      np.array([x["decided_by"] == "human review" for x in d]),
                                      np.array([float(x["probability_against_board"]) for x in d]))
        def for_target(name, target):
            flag, rev, score = systems[name]
            if target == "against the board" and name in against:
                flag, score = against[name]
            return flag, rev, score

        per_year[year] = {"n": len(results), "targets": targets, "meeting": [k[0] for k in keys],
                          "scores": {t: {k: for_target(k, t)[2] for k in systems} for t in targets}}
        for name in systems:
            for target, actual in targets.items():
                flag, rev, score = for_target(name, target)
                row = {"year": year, "system": name, "target": target, "proposals": len(results), **metrics(flag, rev, score, actual)}
                row.update(rank_metrics(score, actual) if name != BOARD else {})
                csv_rows.append(row)

    def get(year, name, target):
        return next((c for c in csv_rows if c["year"] == year and c["system"] == name and c["target"] == target), None)

    def mean(name, target, key, years):
        c = [get(y, name, target) for y in years]
        return sum(x[key] for x in c) / len(c)

    gap = check_against_committed(main_dir, frozen_2026, votes)
    clean_years = [y for y in TEST_YEARS if y != 2026]
    lines = ["# Comparison: marie's Jev pipeline and main's system", "",
             "Produced by `python -m nbim_vote.report_results --main-dir <checkout of main>`. Full numbers in `comparison_with_main.csv`.", "",
             "## How the comparison is made fair", "",
             "- **Same proposals.** Every year, both systems are scored on exactly the proposals both can score "
             "(`data/dirty/real_votes.csv`, rows with a board recommendation and an NBIM vote).",
             "- **Same information.** main's history model freezes its history at the start of each test year; marie uses votes "
             "from earlier dates in the same year. main's model is therefore also run here **with live history**, the same "
             "information marie has. main's own setting is kept as a second row. Both are main's code, run in this process "
             + (f"(its committed 2026 file is reproduced to within {gap:.1e})." if gap is not None else "(no committed file to check against)."),
             "- **Same review effort.** The systems send different shares of proposals to a person (marie about 40%, main about 25%), "
             "so their F1 and \"reaching a person\" are not comparable as run. The headline uses measures that do not depend on that: "
             "average precision, MOT votes caught when each system's ranking picks the same share of proposals, and precision when "
             "each flags as many proposals as there are MOT votes (R-precision).",
             "- **Both targets.** marie is trained to predict NBIM voted MOT; main to predict a vote against the board. "
             "They differ on shareholder proposals and abstentions, so every number is shown for both. For the against-the-board "
             "target, marie's recommendation counts when it departs from the board, and her score is turned around where the "
             "board recommends MOT (as main's combined model does with her scores).",
             "- **Tuning.** marie's design was chosen while looking at 2024-2026 (2026 was run six times). main's history model "
             "has a setting (CLIP) chosen on test years 2022-2025, and its full system was built while 2026 was known. "
             "The headline therefore averages 2022-2025 and shows 2026 on its own.",
             "- **What is being compared.** marie's row is the whole pipeline: an LLM (Jev), company facts from filings, and a "
             "triage model. main's history model uses NBIM's vote history only. marie without Jev (`--no-jev`: triage model, "
             "director rules, code citations) and marie's triage model alone are shown too; the latter is the like-for-like "
             "machine-learning comparison. main's combined model, where present, adds Jev and marie's triage model to main's own "
             "signals and is fitted to predict a vote against the board. It is run three ways: with the scores main committed "
             "(exported from this branch at commit a7d971a), with the scores exported from this branch now, and with this "
             "branch's final recommendation (board-MOT rule, director rules, AVSTÅ) in place of Jev's raw vote. main's full system (rules, AI proxy reading) is only saved for 2026.", "",
             "## Headline: average over 2022-2025, equal review effort", ""]
    out = []
    for target in TARGETS:
        for name in ranked:
            out.append([target, name, f"**{mean(name, target, 'avg_precision', clean_years):.3f}**",
                        *(pct(mean(name, target, f"recall@{int(s * 100)}", clean_years)) for s in SHARES),
                        pct(mean(name, target, "r_precision", clean_years))])
    lines += table(["Target", "System", "Avg precision", *(f"Caught, top {int(s * 100)}% reviewed" for s in SHARES), "R-precision"], out)

    lines += ["", "Differences with 95% intervals (bootstrap over meetings, 2022-2025, years averaged). "
              "An interval that contains 0 means the systems cannot be told apart on these years.", ""]
    out = []
    for target in TARGETS:
        for other in tuple(combined) + (MAIN_LIVE, MAIN_FROZEN, MARIE_NOJEV, MARIE_TRIAGE):
            for measure, label in (("avg_precision", "Avg precision"), ("recall@25", "Caught, top 25%")):
                lo, hi = bootstrap(per_year, clean_years, MARIE, other, target, measure)
                point = mean(MARIE, target, measure, clean_years) - mean(other, target, measure, clean_years)
                fmt = (lambda v: f"{v:+.3f}") if measure == "avg_precision" else (lambda v: f"{100 * v:+.1f} pts")
                out.append([target, f"marie minus {other.split(': ', 1)[1]}", label, fmt(point), f"{fmt(lo)} to {fmt(hi)}"])
    lines += table(["Target", "Comparison", "Measure", "Difference", "95% interval"], out)

    lines += ["", "## 2026 on its own (marie tuned on it)", ""]
    out = []
    for target in TARGETS:
        for name in (*ranked, MAIN_FULL):
            m = get(2026, name, target)
            if m is None:
                continue
            out.append([target, name, f"{m['avg_precision']:.3f}", *(pct(m[f"recall@{int(s * 100)}"]) for s in SHARES), pct(m["r_precision"])])
    lines += table(["Target", "System", "Avg precision", *(f"Caught, top {int(s * 100)}% reviewed" for s in SHARES), "R-precision"], out)

    lines += ["", "## Each year, ranking measures", ""]
    out = []
    for target in TARGETS:
        for year in TEST_YEARS:
            for name in (*ranked, MAIN_FULL):
                m = get(year, name, target)
                if m is None:
                    continue
                out.append([target, year, name, m["positives"], f"{m['avg_precision']:.3f}",
                            *(pct(m[f"recall@{int(s * 100)}"]) for s in SHARES), pct(m["r_precision"])])
    lines += table(["Target", "Year", "System", "Positives", "Avg precision", *(f"Top {int(s * 100)}%" for s in SHARES), "R-precision"], out)

    lines += ["", "## Each system as it runs (own thresholds and review share, not directly comparable)", "",
              "Recommended MOT: marie's recommendation; main's \"likely AGAINST board\" band (full system: suggested MOT or AVSTÅ). "
              "Review: share of proposals a person sees, including every recommended MOT.", ""]
    out = []
    for target in TARGETS:
        for year in TEST_YEARS:
            for name in (MARIE, MARIE_NOJEV, MAIN_FROZEN, MAIN_LIVE, *COMBINED, MAIN_FULL, BOARD):
                m = get(year, name, target)
                if m is None:
                    continue
                dash = name == BOARD
                out.append([target, year, name, pct(m["precision"]), pct(m["recall"]), pct(m["f1"]), m["hits"], m["false_alarms"],
                            "–" if dash else pct(m["review_share"]), "–" if dash else f"{m['reached']}/{m['positives']}"])
    lines += table(["Target", "Year", "System", "Precision", "Recall", "F1", "Hits", "False alarms", "Review", "Reaching a person"], out)
    lines += ["", "## What to keep in mind", "",
              "- marie reuses main's AI proxy facts for US directors and main's CEO pay figures, so part of marie's company-fact "
              "signal is main's work.",
              "- How marie's years were used while designing: " + "; ".join(f"{y} {t}" for y, t in SEEN.items()) + ".",
              "- With 60-110 positives a year, differences of a few votes are noise; use the intervals above.", ""]
    return lines, csv_rows


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--main-dir", help="a checkout of main (its src/benchmark/model.py is run here)")
    a = p.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    s = Setup()
    runs = {(y, f): s.walk_forward(y, f) for y in TEST_YEARS for f in (True, False)}
    runs_nojev = {y: s.walk_forward(y, True, jev=False) for y in TEST_YEARS}
    (OUT / "jev_results.md").write_text("\n".join(my_report(s, runs, runs_nojev)), encoding="utf-8")
    print(f"Wrote {(OUT / 'jev_results.md').relative_to(DATA.parent)}")
    if a.main_dir:
        lines, csv_rows = compare(s, runs, a.main_dir, runs_nojev)
        (OUT / "comparison_with_main.md").write_text("\n".join(lines), encoding="utf-8")
        fields = list(dict.fromkeys(k for r in csv_rows for k in r))
        with open(OUT / "comparison_with_main.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()} for r in csv_rows)
        print(f"Wrote {(OUT / 'comparison_with_main.md').relative_to(DATA.parent)} and comparison_with_main.csv")


if __name__ == "__main__":
    main()
