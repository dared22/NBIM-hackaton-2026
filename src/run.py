"""One command that reproduces every result and writes one decision per proposal.

Run from the repo root (about three minutes, no internet, no API key):
    python3 src/run.py

It writes two files in data/outputs/
    decisions_2026.csv  one row per 2026 proposal: suggested vote, probability,
                        band, whether a person must decide, reasons, guideline,
                        the guideline's own words with its page number,
                        evidence link, and what NBIM actually did
    results.md          the full printed output of every evaluation script

Three sources feed the decisions
    US executive pay votes   src/agent/pay_model.py       vote history + company facts
    US director elections    src/agent/board_rules.py     NBIM's written rules + facts read from the
                                                          proxy (with quotes) and SEC role data, on
                                                          top of the history model. A rule acts alone
                                                          only after NBIM followed it twice in a row
    proposals whose wording  src/agent/proposal_rules.py  NBIM's written rules + the proposal
    decides the vote                                      title, on top of the history model
    all other proposals      src/benchmark/model.py       vote history only

For NBIM's vote file, the probability comes from the combined model
(src/agent/combined_model.py): the history model, main's rules, and the Jev
decision model and second model from Marie's pipeline, weighted by a fit on
earlier years.

A US company's annual pay vote in NBIM's vote file that is also in the SEC file
gets the pay model's answer (src/agent/pay_overlap.py), so each proposal has
one answer.

How a decision is made
    1. Guardrail. Instruction-like wording in the proposal text sends it to a
       person with a security flag. Extra words added to a known item do not
       break the lookup of that item's history. Wording that does not read
       like a ballot item (words no earlier ballot used) also brings in a
       person, so a reworded instruction needs no trigger word to be caught.
       A proxy statement that speaks to an automated reader sends every
       nominee of that meeting to a person.
    2. The model gives the probability that NBIM votes against the board.
    3. Band. Below 5%: follow the board. At or above the model's cut-off:
       vote against the board. In between: a person decides.
    4. Low-information gate. The tool never follows the board on its own when
       it is flying blind: no pay figure for a pay vote, a company it has
       never seen, a missing board recommendation, or figures that look
       wrong all go to a person, whatever the probability says.
    5. Abstain. Where NBIM's earlier against-votes in a market were cast as
       abstentions, an "against the board" suggestion is written as AVSTÅ.

The tool only suggests. It never casts a vote. NBIM's actual vote is joined
in at the very end, for scoring only.
"""

import collections
import csv
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "src", "agent"))

from benchmark import model as bm  # noqa: E402
import board_rules as br  # noqa: E402
import combined_model as cm  # noqa: E402
import country_rules as cr  # noqa: E402
import director_rules as dr  # noqa: E402
import pay_overlap as po  # noqa: E402
import pay_model as pm  # noqa: E402
import proposal_rules as pr  # noqa: E402
import robustness as rb  # noqa: E402
import routing  # noqa: E402
import rule_check as rc  # noqa: E402

OUT = os.path.join(ROOT, "data", "outputs")
YEAR = 2026
USE_COMBINED = True     # False: NBIM's vote file is scored by the history model alone, as before the combined model
SCRIPTS = [
    ("History model, all proposal types", ["src/benchmark/model.py", "--data", "data/dirty/real_votes.csv"]),
    ("History model, repeated for 2022-2026", ["src/benchmark/model.py", "--data", "data/dirty/real_votes.csv", "--walk-forward"]),
    ("Pay model, US executive pay votes", ["src/agent/pay_model.py"]),
    ("Pay model, how the inputs were chosen (training seasons only)", ["src/agent/pay_model.py", "--develop"]),
    ("The same US pay proposals in both files: which model should answer?", ["src/agent/pay_overlap.py"]),
    ("Director elections at US companies: NBIM's written rules applied to dated facts", ["src/agent/director_rules.py"]),
    ("Director elections at US companies: facts read from the proxy, and rules that must earn trust", ["src/agent/board_rules.py"]),
    ("How reliable is the proxy reader? A second, stronger model read a sample again", ["src/agent/board_reader_check.py"]),
    ("Proposals whose wording decides the vote: NBIM's written rules applied to the title", ["src/agent/proposal_rules.py"]),
    ("Experiment: do ballot details improve the history model? (test years 2022-2025)", ["src/agent/history_model.py"]),
    ("Guideline rule check", ["src/agent/rule_check.py"]),
    ("Position papers: do they add anything?", ["src/agent/position_papers_test.py"]),
    ("The judge: an AI model weighs the gathered facts against NBIM's rules and record", ["src/agent/judge.py"]),
    ("The combined model: both teams' systems in one score", ["src/agent/combined_model.py"]),
    ("Director elections in Japan and Korea: a company fact that brings in a person", ["src/agent/country_rules.py"]),
    ("Policy watch: has NBIM reworded a rule since the stored edition?", ["src/agent/policy_watch.py"]),
    ("Confidence and routing: when should the tool ask a person?", ["src/agent/routing.py"]),
    ("Pilot: does how the CEO's pay is built explain the pay against-votes?", ["src/agent/pay_structure_test.py"]),
    ("Jev as a judge of US pay votes (the pay model's twelfth input)", ["src/agent/jev_pay.py"]),
    ("Resistance test and guardrail", ["src/agent/robustness.py"]),
    ("Resistance test 2: a reworded instruction against the whole pipeline", ["src/agent/paraphrase_test.py"]),
    ("Resistance test 3: an instruction planted in the proxy the AI reader reads", ["src/agent/reader_injection_test.py"]),
]
COLS = ["dataset", "key", "meeting_date", "company", "proposal", "board_recommendation", "suggested_vote",
        "probability_against_board", "band", "decided_by", "review_reason", "model", "reasons",
        "guideline", "guideline_text", "evidence_url", "actual_against_board", "actual_vote"]
RULE_ID = re.compile(r"\brule (\d+\.\d+(?:-AT)?\.\d+)")
GVG_ID = re.compile(r"GVG (\d+\.\d+(?:-AT)?(?:\.\d+)?)")


def opposite(vote):
    return {"FOR": "MOT", "MOT": "FOR"}.get(vote, "")


def decide(board, band, flags):
    """Suggested vote and who decides. `flags` are reasons a person must look."""
    if not board:
        flags = flags + ["the board's recommendation is missing"]
    if band == "send to human":
        flags = ["the model is unsure"] + flags
    vote = opposite(board) if band == "likely AGAINST board" and board else board
    return vote, ("human review" if flags else "automatic"), "; ".join(flags)


_PAY = []


def pay_once():
    """The pay decisions, computed once per run."""
    if not _PAY:
        _PAY.append(pay_decisions())
    return _PAY[0]


def general_decisions(rows=None, pay=None):
    """All proposal types from NBIM's published votes: history model plus NBIM's written rules.
    A US company's annual pay vote that is also in the SEC file gets the pay model's answer.

    `rows` can be passed in to score altered proposals (the resistance check in tests).
    """
    rows = bm.read_votes(rc.VOTES) if rows is None else rows
    col = {c: i for i, c in enumerate(COLS)}
    pay_index = po.build_index([(d[col["company"]], d[col["meeting_date"]], d) for d in (pay_once() if pay is None else pay)])
    # Guardrail, part 2: if a proposal's text is an item this company has voted on
    # before plus extra words, the known item is used for the history lookup.
    year = lambda r: int(r["meeting_date"][:4])
    rb.restore_known_items([r for r in rows if year(r) == YEAR], [r for r in rows if year(r) < YEAR])
    sections = rc.load_guidelines()
    cand = rc.candidate_sections(rows, sections)
    _, val, _, _ = bm.run_year(rows, YEAR - 1)
    train, test, w, thr = bm.run_year(rows, YEAR)
    known_companies = {r["company_id"] for r in train}
    vocabulary = rb.ballot_vocabulary(r["proposal_text"] for r in train)
    # The combined model: the history model's probability, main's rules, and the two scores exported
    # from Marie's pipeline (Jev and her second model), weighted by a fit on earlier years.
    combo_fit, combo_level = cm.fitted(YEAR)
    components = cm.load_components(YEAR)
    abstain = routing.abstain_markets(train)
    papers = rc.load_papers()
    citations = rc.load_citations()
    cache = rc.load_cache()
    rc.attach_scores(val, cand, sections, cache)
    rc.attach_scores(test, cand, sections, cache)
    directors = {(r["meeting_id"], r["item_no"]): r for r in br.load_scored()}
    worded = {(r["meeting_id"], r["item_no"]): r for r in pr.load_scored() if r["rules"]}
    scored = [r for r in val if r["rule_p"] is not None]
    rule_thr = bm.best_f1_threshold([r["rule_p"] for r in scored], [r["y"] for r in scored]) if scored else 1.0
    out = []
    for r in test:
        hits = rb.guard_patterns(r["proposal_text"])
        flags = ["security flag: " + ", ".join(hits)] if hits else []
        if r["company_id"] not in known_companies:
            flags.append("low information: no earlier votes at this company")
        key = (r["meeting_id"], r["item_no"])
        comp = components.get(key) if USE_COMBINED else None
        prob, band, model, reasons, guide = r["p"], r["band"], "vote history", bm.reasons(w, r["x"]), None
        if comp:
            judged = cm.judge_answer(r, directors.get(key))
            prob = cm.score(combo_fit, cm.inputs_for(r, comp, directors.get(key), worded.get(key), judged["p"] if judged else None))
            band = ("likely AGAINST board" if prob >= combo_level else "likely WITH board" if prob < cm.LOW else "send to human")
            model = "combined model: vote history, Jev and a second model"
            if judged:
                model = "combined model: vote history and a judge model weighing the proxy facts"
                if judged["p"] >= 0.2:
                    reasons += f" | the judge model puts this at {judged['p']:.0%}: {judged['reason']}"
            if comp["jev_vote"] != r["mgmt_rec"] and r["mgmt_rec"]:
                reasons += (f" | the Jev decision model recommends {comp['jev_vote']}"
                            + (f", citing GVG {comp['jev_cited_section']}" if comp["jev_cited_section"] else ""))
        if hits:
            band = "send to human"
        d = directors.get(key) if directors.get(key, {}).get("rules") else worded.get(key)
        if d and d["rules"]:
            active = [(c, t) for c, t in d["rules"] if d["rule_state"][c] == "active"]
            model = "NBIM rule + facts from the proxy and SEC filings" if key in directors and directors[key]["rules"] else "NBIM rule + proposal wording"
            reasons = " | ".join(t for _, t in d["rules"])
            guide = ", ".join(dict.fromkeys(c for c, _ in d["rules"]))
            if active and not hits:
                band = "likely AGAINST board"
                # A written rule with its fact does not depend on the company's vote history.
                flags = [f for f in flags if not f.startswith("low information")]
            elif d.get("hold_reason"):
                flags.append("a rule applies but the tool does not act on it alone: " + d["hold_reason"])
            else:
                flags.append("rule suspended: NBIM supported the board the last two times " +
                             ", ".join(c for c, _ in d["rules"]) + " applied")
        by_pay = po.find(pay_index, r["company"], r["meeting_date"]) if po.is_annual_pay_vote(r) else None
        if by_pay:
            # The same proposal is scored with company facts by the pay model: use that answer.
            model, prob = "vote history + company facts (pay model)", float(by_pay[col["probability_against_board"]])
            band = "send to human" if hits else by_pay[col["band"]]
            reasons = by_pay[col["reasons"]]
            flags = (["security flag: " + ", ".join(hits)] if hits else []) + [
                f for f in by_pay[col["review_reason"]].split("; ")
                if f and f != "the model is unsure" and not f.startswith("security flag")]
        # Guardrail, part 3: wording that does not read like a ballot item brings in a person, whatever
        # the models say. The suggestion is kept; the person decides.
        odd = rb.unusual_wording(r["proposal_text"], vocabulary)
        if odd and not hits:
            flags.append("security flag: the wording does not read like a ballot item (words no earlier ballot used: "
                         + ", ".join(odd[:6]) + ")")
        # Guardrail, part 4: the proxy the AI reader read speaks to an automated reader. The facts read
        # from it are shown, and a person decides.
        if directors.get(key, {}).get("proxy_alert"):
            flags.append('security flag: the proxy statement holds wording addressed to an automated reader ("'
                         + directors[key]["proxy_alert"][:120] + '")')
        # The tool acts alone on "against" only when the suggestion rests on something a person can
        # check: a rule with its fact, the pay figures, or NBIM's own against-vote on the item last time.
        if (comp and not by_pay and band == "likely AGAINST board" and not (d and d["rules"])
                and r["prev_same_item"] != 1):
            flags.append("the models suggest a vote against the board, but no rule, fact or earlier "
                         "against-vote on this item backs it")
        # Japan and Korea: a company fact NBIM often acts on brings in a person, unless the tool
        # is already acting alone on "against".
        fact = cr.signal_for(r)
        if fact:
            reasons += " | " + fact[1]
            if not (band == "likely AGAINST board" and not flags):
                flags.append("a company fact applies that NBIM often acts on (see the reasons)")
        vote, who, why = decide(r["mgmt_rec"], band, flags)
        market = (r["country"], r["proposal_type"])
        if vote == "MOT" and band == "likely AGAINST board" and market in abstain:
            # In a few markets NBIM casts its against-votes as abstentions (learned from earlier years).
            vote = "AVSTÅ"
            reasons += (f" | in {r['country']} NBIM cast {abstain[market][0]} of its {abstain[market][1]} earlier "
                        f"against-votes on this proposal type as abstentions")
        if guide:
            pass
        elif fact and fact[0]:
            guide = f"{fact[0]} (NBIM's usual stated reason for against-votes on directors in this market)"
        elif r["rule_p"] is not None and r["rule_p"] >= rule_thr:
            guide = f"GVG {r['rule_section']} (rule check, probability {r['rule_p']:.2f})"
        elif comp and comp["jev_cited_section"] and comp["jev_vote"] != r["mgmt_rec"] and band != "likely WITH board":
            guide = f"GVG {comp['jev_cited_section']} (named by the Jev decision model)"
        elif band != "likely WITH board" and r["candidates"]:
            guide = f"GVG {r['candidates'][0]} (NBIM's most common stated reason for this proposal type before 2025)"
        else:
            guide = ""
        evidence = ""
        if d and d["rules"] and "f" in d:
            evidence = d.get("evidence_url") or (
                f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={d['f']['person_cik']}&type=4"
                if d["f"] and d["f"].get("matched") else "")
        # The words of the guideline and the page they are on. A rule that fired is quoted
        # itself; otherwise the cited section's introduction is quoted.
        quoted = rc.quote((RULE_ID.findall(reasons) if d and d["rules"] else []) or GVG_ID.findall(guide), citations)
        if by_pay:
            guide, quoted, evidence = by_pay[col["guideline"]], by_pay[col["guideline_text"]], by_pay[col["evidence_url"]]
        elif guide:   # name NBIM's position paper for the cited section, as NBIM does in its own rationales
            rule_id = d["rule"][0] if d and d["rules"] and d.get("rule") else ""
            paper = rc.paper_for(papers, guide.split(" (")[0].split(",")[0], rule_id)
            if paper:
                guide += f"; position paper: {paper['title']} ({paper['url']})"
        out.append(["NBIM votes, all proposal types", f"{r['meeting_id']}-{r['item_no']}", r["meeting_date"], r["company"],
                    r["proposal_text"], r["mgmt_rec"], vote, f"{prob:.3f}", band, who, why, model,
                    reasons, guide, quoted, evidence, r["y"], r["nbim_vote"]])
    return out


def pay_decisions():
    """US executive pay votes, history plus company facts."""
    rows, _ = pm.load_rows()
    _, test, w, ps, thr = pm.score_test_season(rows)
    pay_paper = rc.paper_for(rc.load_papers(), "GVG 3.3")
    citations = rc.load_citations()
    out = []
    for r, p in zip(test, ps):
        flags = [("low information: " if "no pay figure" in f else "check the figures: ") + f for f in pm.warnings_for(r)]
        hits = rb.guard_patterns(r["forslag"])
        if hits:
            flags.append("security flag: " + ", ".join(hits))
        band = "send to human" if hits else pm.band_of(p, thr)
        # Low support at the last pay vote: a vote the model would wave through goes to a person instead.
        if band == "likely WITH board" and pm.low_support_note(r):
            flags.append(pm.low_support_note(r))
        # Every say-on-pay proposal is recommended FOR by the board.
        vote, who, why = decide("FOR", band, flags)
        why_pay = pm.reasons(r, w)
        codes = ", ".join(sorted({c for _, c in why_pay if c}))
        notes = pm.structure_notes(r)
        out.append(["NBIM pay votes, US filers", f"{r['cusip']}-{r['moetedato']}", r["moetedato"], r["utsteder"],
                    r["forslag"], "FOR", vote, f"{p:.3f}", band, who, why, "vote history + company facts",
                    " | ".join(t for t, _ in why_pay) + (
                        " | read from the proxy, shown as evidence and not part of the score: " + "; ".join(notes) if notes else ""),
                    codes + (f"; position paper: {pay_paper['title']} ({pay_paper['url']})" if why_pay and pay_paper else ""),
                    rc.quote(GVG_ID.findall(codes), citations),
                    r["c"].get("url", ""), r["y"], "MOT" if r["stemme"] in ("AGAINST", "WITHHOLD") else "FOR"])
    return out


def summary(rows, name):
    """Counts that describe the human workload and what the machine gets right alone."""
    n = len(rows)
    col = {c: i for i, c in enumerate(COLS)}
    against = [r for r in rows if r[col["actual_against_board"]] == 1]
    auto = [r for r in rows if r[col["decided_by"]] == "automatic"]
    auto_against = [r for r in auto if r[col["band"]] == "likely AGAINST board"]
    gated = [r for r in rows if r[col["decided_by"]] == "human review" and r[col["band"]] == "likely WITH board"]
    review = [r for r in rows if r[col["decided_by"]] == "human review"]
    hit = lambda group: sum(1 for r in group if r[col["actual_against_board"]] == 1)
    lines = [f"### {name}",
             f"- Proposals: {n}; NBIM voted against the board on {len(against)}.",
             f"- Decided automatically: {len(auto)} ({len(auto) / n:.0%}). Sent to a person: {len(review)} ({len(review) / n:.0%}).",
             f"- Automatic 'against the board' suggestions: {len(auto_against)}, of which {hit(auto_against)} were right "
             f"(precision {hit(auto_against) / len(auto_against):.0%}, recall {hit(auto_against) / len(against):.0%})."
             if auto_against else "- No automatic 'against the board' suggestions.",
             f"- Against-votes inside the pile sent to a person: {hit(review)} "
             f"({hit(review) / len(against):.0%} of all against-votes).",
             f"- Against-votes the tool waved through with the board: "
             f"{hit([r for r in auto if r[col['band']] == 'likely WITH board'])} "
             f"({hit([r for r in auto if r[col['band']] == 'likely WITH board']) / len(against):.0%} of all against-votes).",
             f"- With a person reading the review pile, {hit(auto_against) + hit(review)} of {len(against)} against-votes "
             f"are either suggested or seen ({(hit(auto_against) + hit(review)) / len(against):.0%}).",
             f"- Sent to a person although the model's probability was low (nothing to go on, or a rule applies that "
             f"the tool does not act on alone): {len(gated)} proposals; {hit(gated)} of them were against-votes."]
    return "\n".join(lines)


def headline(general, pay):
    """The numbers for a slide, as a short Markdown page: both test sets, the simple rules, the tool."""
    col = {c: i for i, c in enumerate(COLS)}
    pct = lambda a, b: f"{a / b:.0%}" if b else "-"

    def tool(rows):
        against = [r for r in rows if r[col["actual_against_board"]] == 1]
        alone = [r for r in rows if r[col["band"]] == "likely AGAINST board" and r[col["decided_by"]] == "automatic"]
        person = [r for r in rows if r[col["decided_by"]] == "human review"]
        hit = lambda g: sum(1 for r in g if r[col["actual_against_board"]] == 1)
        return len(rows), len(against), len(alone), hit(alone), len(person), hit(person)

    def table(rows):
        return ["| Method | Says against | Right | Wrong | Precision | Recall |", "|---|---|---|---|---|---|"] + [
            f"| {name} | {flags} | {hits} | {flags - hits} | {pct(hits, flags)} | {pct(hits, total)} |" for name, flags, hits, total in rows]

    votes = bm.read_votes(rc.VOTES)
    _, test_a, _, _ = bm.run_year(votes, YEAR)
    last_a = [r for r in test_a if r["prev_same_item"] == 1]
    n, a, alone, right, person, seen = tool(general)
    lines = [f"# Headline numbers, test year {YEAR}", "",
             "Written by `python3 src/run.py`. The year was not used to fit or choose anything, except where "
             "`docs/model-card.md` says how often it has been scored.", "",
             f"## NBIM's vote file, all countries: {n} proposals, {a} against the board", "",
             f"Always following the board is right on {pct(n - a, n)} of proposals and finds none of the {a}.", ""]
    lines += table([("Always follow the board", 0, 0, a), ("Same as last time at this company", len(last_a), sum(r["y"] for r in last_a), a),
                    ("The tool, acting alone", alone, right, a)])
    lines += ["", f"The tool sends {person} proposals ({pct(person, n)}) to a person, and {seen} against-votes are among them. "
              f"So {right + seen} of the {a} against-votes ({pct(right + seen, a)}) are either suggested by the tool or put in front of a person, "
              f"and {a - right - seen} are waved through.", ""]

    # The reading dial: the 5% level is a setting. What a lower level costs and catches.
    waved = sorted((r for r in general if r[col["decided_by"]] == "automatic" and r[col["band"]] == "likely WITH board"),
                   key=lambda r: -float(r[col["probability_against_board"]]))
    careful = cm.careful_level(YEAR)
    lines += ["### If a person reads more", "",
              f"The {cm.LOW:.0%} level, below which the tool follows the board on its own, is a setting. Lower it and more proposals go to a "
              "person, in the order of the tool's own probability. The careful level is the one that would have put "
              f"{cm.CAREFUL_TARGET:.0%} of the against-votes of the earlier years ({cm.DEVELOP[0]}-{cm.DEVELOP[-1]}) in front of a person or in "
              f"the tool's own suggestions. It was chosen on those years only.", "",
              "| Level | Sent to a person | Share | Against-votes suggested or seen | Waved through |", "|---|---|---|---|---|"]
    for name, level in sorted(((f"{cm.LOW:.0%} (as above)", None), ("3%", 0.03), ("2%", 0.02), (f"Careful level, {careful:.1%}", careful), ("1%", 0.01)),
                              key=lambda item: -(item[1] if item[1] is not None else cm.LOW)):
        extra = [r for r in waved if level is not None and float(r[col["probability_against_board"]]) >= level]
        caught = right + seen + sum(1 for r in extra if r[col["actual_against_board"]] == 1)
        lines.append(f"| {name} | {person + len(extra)} | {pct(person + len(extra), n)} | {caught} of {a} ({pct(caught, a)}) | {a - caught} |")
    lines += ["", "The proposals a lower level adds are the rows of `data/outputs/decisions_2026.csv` decided automatically with the board, "
              "sorted by `probability_against_board`.", ""]

    pay_rows, _ = pm.load_rows()
    test_b = [r for r in pay_rows if r["season"] == pm.TEST_SEASON]
    last_b = [r for r in test_b if r["prev"] == 1]
    big_b = [r for r in test_b if r["pay"] and r["pay"] >= pm.STRICT_LEVEL]
    n, a, alone, right, person, seen = tool(pay)
    lines += [f"## US executive pay votes: {n} votes, {a} against the board", "",
              f"Always following the board is right on {pct(n - a, n)} of votes and finds none of the {a}.", ""]
    lines += table([("Always follow the board", 0, 0, a), ("Same as last season", len(last_b), sum(r["y"] for r in last_b), a),
                    ("Against if the CEO is paid 25 million dollars or more", len(big_b), sum(r["y"] for r in big_b), a),
                    ("The tool, acting alone", alone, right, a)])
    lines += ["", f"The tool sends {person} votes ({pct(person, n)}) to a person, and {seen} against-votes are among them. "
              f"So {right + seen} of the {a} against-votes ({pct(right + seen, a)}) are either suggested or seen, "
              f"and {a - right - seen} are waved through.", "",
              "## How to read these", "",
              "- \"Says against\" for the tool counts only what it suggests on its own. What it sends to a person is counted in the sentence under each table.",
              "- The two test sets are separate files and do not add up to one total.",
              "- Intervals, the earlier years and everything that was tested and left out are in `data/outputs/results.md` and `docs/model-card.md`.", ""]
    return "\n".join(lines)


def main():
    os.makedirs(OUT, exist_ok=True)
    parts = ["# Results", "", f"Produced by `python3 src/run.py`. Test year {YEAR}; nothing from {YEAR} is used to fit or tune.", ""]

    pay = pay_once()
    general = general_decisions(pay=pay)
    with open(os.path.join(OUT, f"decisions_{YEAR}.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(COLS)
        w.writerows(sorted(pay + general, key=lambda r: -float(r[7])))
    parts += ["## Decisions", "", "One row per proposal is in `data/outputs/decisions_2026.csv`.", "",
              summary(pay, "US executive pay votes (history + company facts)"), "",
              summary(general, "All proposal types (combined model, plus NBIM rules for US directors and worded proposals)"), ""]

    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"))
    for title, args in SCRIPTS:
        print(f"running: {title} ...", flush=True)
        done = subprocess.run([sys.executable] + args, cwd=ROOT, env=env, capture_output=True, text=True)
        if done.returncode != 0:
            raise SystemExit(f"{args[0]} failed:\n{done.stderr[-2000:]}")
        parts += [f"## {title}", "", f"`python3 {' '.join(args)}`", "", "```text", done.stdout.rstrip(), "```", ""]

    with open(os.path.join(OUT, "results.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    with open(os.path.join(OUT, "headline.md"), "w", encoding="utf-8") as f:
        f.write(headline(general, pay))
    print()
    print(summary(pay, "US executive pay votes (history + company facts)"))
    print()
    print(summary(general, "All proposal types (combined model, plus NBIM rules for US directors and worded proposals)"))
    # The same decisions in the column layout of the team's demo (branch marie, src/nbim_vote/dashboard.py).
    import export_for_dashboard
    export_for_dashboard.main()
    print(f"\nWrote data/outputs/decisions_{YEAR}.csv ({len(pay) + len(general)} proposals), data/outputs/results.md "
          f"and data/outputs/headline.md")


if __name__ == "__main__":
    main()
