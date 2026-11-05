"""Proposals whose wording decides the vote: NBIM's written rules applied to the text.

Run from the repo root (no internet, no API key, no AI model):
    python3 src/agent/proposal_rules.py

Idea
    Some of NBIM's rules are about what a proposal asks for, and the proposal
    title says it. For example
        3.1.2     "We will support a proposal to declassify the board."
        4.2.2     support for the right "to act by written consent"
        6.2-AT.3  "We will support a proposal to abolish anti-takeover measures."
    When the board recommends against such a proposal, the rule says NBIM
    votes for it, which is a vote against the board. No training is needed, so
    every year in the file is a test year.

Only rules whose condition can be read from the title are used: the ones the
guidelines mark as clear-cut, plus rule 5.2.2, which names the agenda item
"other business" in its own text. Rules that need judgement (sustainability
reporting, "best interest of shareholders") are left to a person.

Honest note: the rules are NBIM's. The wording patterns that recognise them
were written after looking at the list of proposal titles in the file, so they
were not written blind.

The drift monitor from director_rules.py watches each rule: after NBIM has
gone the other way on a rule's last two cases, the rule is suspended and its
cases go to a person.

Answer key: data/dirty/real_votes.csv, all countries. The rule decisions use
no votes. The monitor and the scoring do.
"""

import collections
import csv
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "src", "agent"))
from benchmark import model as bm  # noqa: E402
from director_rules import run_monitor  # noqa: E402

VOTES = os.path.join(ROOT, "data", "dirty", "real_votes.csv")
OUT = os.path.join(ROOT, "data", "outputs", "proposal_rules.csv")

# (rule id, guideline section, what NBIM does, wording that shows the proposal asks for it)
RULES = [
    ("1.3.3", "GVG 1.3", "FOR", "separate the roles of chairperson and CEO",
     r"^(require|adopt|appoint|establish)\b.{0,40}(?<!non-)independent (board )?chair|separate .{0,60}chair"),
    ("3.1.2", "GVG 3.1", "FOR", "declassify the board", r"\bdeclassify"),
    ("3.1.5", "GVG 3.1", "FOR", "majority requirements in director elections",
     r"majority vot\w+ (standard )?(for|in) (the )?election of directors"),
    ("3.1.8", "GVG 3.1", "FOR", "proxy access", r"proxy access"),
    ("4.2.2", "GVG 4.2", "FOR", "right to act by written consent", r"act by written consent"),
    ("6.2-AT.3", "GVG 6.2", "FOR", "abolish an anti-takeover measure (supermajority requirement)",
     r"simple majority vote|(reduce|eliminate|remove) (the )?supermajority"
     r"|(remove|abolish|eliminate|repeal) .{0,40}(takeover defen[cs]e|poison pill|rights plan)"),
    ("3.1.1", "GVG 3.1", "MOT", "classify (stagger) the board", r"\bclassify the board|stagger\w* board"),
    ("6.2-AT.2", "GVG 6.2", "MOT", "introduce or renew an anti-takeover measure (poison pill)",
     r"poison pill|shareholder rights plan|takeover defen[cs]e"),
    # The guidelines mark 5.2.2 as needing judgement, but the rule names this agenda item itself:
    # "insufficient to make an informed decision, e.g. the agenda item 'other business'".
    ("5.2.2", "GVG 5.2", "MOT", "vote on unspecified \"other business\"", r"^(transact )?other business\b"),
]


def match_rule(text):
    """The first clear-cut rule the proposal wording falls under, or None."""
    t = text.lower()
    # 'Require Shareholder Approval of Poison Pill' asks to restrict a pill: that is a different rule.
    if re.search(r"(submit|require|subject) .*(poison pill|rights plan).* (to|shareholder) (a )?(shareholder )?(vote|approval)", t):
        return None
    for rule in RULES:
        if re.search(rule[4], t):
            return rule
    return None


def load_scored():
    """Every proposal in the file with the rule it falls under, NBIM's vote by rule, and the monitor's state."""
    rows = bm.read_votes(VOTES)
    bm.add_history_features(rows)      # only for the "same as last time" baseline
    for r in rows:
        rule = match_rule(r["proposal_text"])
        r["rule"] = rule
        r["rule_vote"] = rule[2] if rule else ""
        # The rule gives NBIM's vote. It is "against the board" only when the board recommends the opposite.
        against_board = bool(rule) and r["mgmt_rec"] in ("FOR", "MOT") and rule[2] != r["mgmt_rec"]
        r["rules"] = [(rule[1], f"rule {rule[0]}: the proposal asks to {rule[3]}; NBIM's rule says vote {rule[2]}, "
                                f"the board recommends {r['mgmt_rec']}")] if against_board else []
    run_monitor(rows)
    return rows


def main():
    rows = load_scored()
    C = collections.Counter
    covered = [r for r in rows if r["rule"]]
    against = [r for r in rows if r["y"]]
    sh = [r for r in rows if r["proponent"] == "Shareholder"]
    print(f"All proposals in NBIM's file: {len(rows)}, {len(against)} against the board, "
          f"{min(r['meeting_date'] for r in rows)[:4]}-{max(r['meeting_date'] for r in rows)[:4]}")
    print(f"Proposals whose wording falls under a clear-cut rule: {len(covered)} "
          f"({sum(1 for r in covered if r['proponent'] == 'Shareholder')} from shareholders, "
          f"{sum(1 for r in covered if r['proponent'] != 'Shareholder')} from management)\n")

    print("1. Does NBIM vote as its rule says?")
    out = []
    for rule in RULES:
        b = [r for r in covered if r["rule"][0] == rule[0]]
        if b:
            same = sum(1 for r in b if r["nbim_vote"] == rule[2])
            out.append([rule[0], rule[3][:52], rule[2], len(b), same, f"{same / len(b):.0%}",
                        sum(1 for r in b if r["rules"]), sum(1 for r in b if r["rules"] and r["y"])])
    bm.table(["Rule", "The proposal asks to", "Rule says", "Proposals", "NBIM voted so", "Share",
              "Board said the opposite", "of which NBIM against the board"], out)

    print("\n2. As a predictor of 'against the board' on shareholder proposals (no training, all years)")
    shy = [r for r in sh if r["y"]]
    out = []
    for lab, flagged in (("Always with board", []), ("Same as last time", [r for r in sh if r["prev_same_item"] == 1]),
                         ("Clear-cut rules from the wording", [r for r in sh if r["rules"]]),
                         ("Same as last time, or a rule", [r for r in sh if r["rules"] or r["prev_same_item"] == 1])):
        hits = sum(r["y"] for r in flagged)
        out.append([lab, len(flagged), hits, len(flagged) - hits, f"{hits / len(flagged):.0%}" if flagged else "-",
                    f"{hits / len(shy):.0%}"])
    print(f"   {len(sh)} shareholder proposals with an answer, {len(shy)} against the board")
    bm.table(["Method", "Flags", "Hits", "False alarms", "Precision", "Recall"], out)

    print("\n   All proposals where a rule means 'against the board' (management and shareholder proposals)")
    fired_all = [r for r in rows if r["rules"]]
    same_last = [r for r in fired_all if r["prev_same_item"] == 1]
    new_items = [r for r in fired_all if r["prev_same_item"] != 1]
    print(f"   {len(fired_all)} proposals, {sum(r['y'] for r in fired_all)} against the board. 'Same as last time' covers "
          f"{len(same_last)} of them; the other {len(new_items)} are first-time items it cannot flag, and "
          f"{sum(r['y'] for r in new_items)} of those were against-votes.")

    print("\n3. By period, with the drift monitor")
    out = []
    fired = [r for r in rows if r["rules"]]
    for lab, keep in (("2019-2025", lambda y: y <= "2025"), ("2026", lambda y: y == "2026"), ("all years", lambda y: True)):
        f = [r for r in fired if keep(r["meeting_date"][:4])]
        a = [r for r in f if any(v == "active" for v in r["rule_state"].values())]
        h = [r for r in f if r not in a]
        out.append([lab, f"{sum(r['y'] for r in f)}/{len(f)}", f"{sum(r['y'] for r in a)}/{len(a)}", f"{sum(r['y'] for r in h)}/{len(h)}"])
    bm.table(["Years", "Rules alone: hits/flags", "Monitor: automatic hits/flags", "Monitor: sent to a person, against/total"], out)

    print("\n4. Does the tool cite the section NBIM itself gave?")
    hit = [r for r in fired if r["y"] and r["rationale_section"]]
    print(f"   Of {len(hit)} rule hits where NBIM gave a reason, the tool's section matches NBIM's in "
          f"{sum(1 for r in hit if r['rationale_section'] == r['rule'][1])}: "
          f"{dict(C((r['rule'][1], r['rationale_section']) for r in hit))}")

    print("\n5. Against-votes on shareholder proposals that no clear-cut rule covers, by NBIM's stated reason")
    print("   ", dict(C(r["rationale_section"] or "none given" for r in shy if not r["rules"]).most_common()))
    print("    GVG 5.3 is sustainability reporting, where every rule needs judgement.")

    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["meeting_id", "item_no", "meeting_date", "company", "country", "proponent", "proposal_text",
                    "board_recommendation", "rule", "rule_says", "against_board_by_rule", "rule_state",
                    "nbim_vote", "actual_against_board", "nbim_stated_reason"])
        for r in covered:
            w.writerow([r["meeting_id"], r["item_no"], r["meeting_date"], r["company"], r["country"], r["proponent"],
                        r["proposal_text"], r["mgmt_rec"], r["rule"][0], r["rule"][2], int(bool(r["rules"])),
                        ", ".join(f"{k} {v}" for k, v in r["rule_state"].items()), r["nbim_vote"], r["y"], r["rationale_section"]])
    print(f"\nWrote {len(covered)} proposals to {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
