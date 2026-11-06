"""Voting policy, proposal and country signals, and abstention habits."""

import collections
import csv
import difflib
import html
import json
import os
import re

from src import data as paths
from src.models import history as bm
from src.rules.directors import run_monitor

STORED = paths.GUIDELINES

LIVE = paths.LIVE_GUIDELINES


def plain(text):
    """Lower case, straight quotes, single spaces: for comparing sentences, not for showing them."""
    text = (
        html.unescape(text).replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    )
    return re.sub(r"\s+", " ", text).strip().lower()


def softened(old, new):
    """True when the live wording is weaker than the stored one: "will not" or "will" became "may"."""
    return bool(
        re.search(r"\bwe will\b", plain(old))
        and re.search(r"\bwe may\b", plain(new))
        and not re.search(r"\bwe may\b", plain(old))
    )


def compare(stored_rules, live_sentences, intro_sentences=()):
    """Returns (same, reworded, gone, new). reworded: (rule id, stored text, live text, softened?).
    intro_sentences: the stored edition's introductions, which are on the page too and are not rules."""
    intros = " ".join(plain(s) for s in intro_sentences)
    live = {plain(s): s for s in live_sentences if plain(s) not in intros}
    stored = {plain(r["tekst"]): r for r in stored_rules}
    same = [r["id"] for key, r in stored.items() if key in live]
    unmatched_live = [s for key, s in live.items() if key not in stored]
    reworded, gone = [], []
    for key, r in stored.items():
        if key in live:
            continue
        close = difflib.get_close_matches(key, [plain(s) for s in unmatched_live], n=1, cutoff=0.8)
        if close:
            text = next(s for s in unmatched_live if plain(s) == close[0])
            unmatched_live.remove(text)
            reworded.append((r["id"], r["tekst"], text, softened(r["tekst"], text)))
        else:
            gone.append((r["id"], r["tekst"]))
    return same, reworded, gone, unmatched_live


def softened_rules():
    """Rule ids whose live wording is softer than the stored edition, with the date the page was fetched.
    Empty if no copy of the live page has been saved."""
    if not os.path.exists(LIVE):
        return {}, ""
    with open(LIVE, encoding="utf-8") as f:
        live = json.load(f)
    with open(STORED, encoding="utf-8") as f:
        stored = json.load(f)
    _, reworded, _, _ = compare(stored["regler"], live["sentences"], introductions(stored))
    return {rid: new for rid, _, new, soft in reworded if soft}, live["fetched"]


def introductions(stored):
    return [s for u in stored["underseksjoner"] for s in u.get("innledning", [])] + [
        p["tekst"] for p in stored.get("prinsipper", [])
    ]


VOTES = paths.VOTES

FACTS = paths.COMPANY_FACTS

TOP_TITLE = re.compile(r"会長|社長")

NOT_TOP = re.compile(r"副社長|副会長")

INDEPENDENT_ENOUGH = 0.5


def load_facts():
    with open(FACTS, encoding="utf-8", newline="") as handle:
        return {(r["meeting_id"], r["item_no"]): r for r in csv.DictReader(handle)}


def number(fact, key):
    return float(fact[key]) if fact and fact.get(key, "") != "" else None


def japan_role(fact):
    """The nominee's role in the EDINET report, or None when the report or the nominee was not found."""
    if not fact or fact["jp_found"] != "1" or number(fact, "jp_nominee_found") != 1:
        return None
    if number(fact, "jp_nominee_representative") == 1:
        title = fact["jp_nominee_title"]
        return (
            "top executive"
            if TOP_TITLE.search(title) and not NOT_TOP.search(title)
            else "other representative director"
        )
    if number(fact, "jp_nominee_outside") == 1:
        return "outside director"
    return "other executive" if number(fact, "jp_nominee_executive") == 1 else "inside director"


def signal_for(row, facts=None):
    """(guideline section, the fact in words) when a fact applies that should bring in a person, else None."""
    if row["proposal_type"] != "DIRECTOR_ELECTION":
        return None
    fact = (load_facts() if facts is None else facts).get((row["meeting_id"], row["item_no"]))
    if row["country"] == "Japan":
        share = number(fact, "jp_independent_share")
        if japan_role(fact) == "top executive" and share is not None and share < INDEPENDENT_ENOUGH:
            return (
                "GVG 1.1",
                f"the nominee is the company's top executive ({fact['jp_nominee_title'][:24]}, a representative "
                f"director) and {share:.0%} of the proposed board is independent, from the EDINET report filed before "
                f"the meeting; in Japan NBIM's against-votes fall on the top executive at boards like this",
            )
    if row["country"] == "South Korea" and "inside director" in row["proposal_text"].lower():
        return (
            "",
            "the ballot names this nominee an inside director; NBIM opposes about one in four inside directors in Korea",
        )
    return None


RULES = [
    (
        "1.3.3",
        "GVG 1.3",
        "FOR",
        "separate the roles of chairperson and CEO",
        r"^(require|adopt|appoint|establish)\b.{0,40}(?<!non-)independent (board )?chair|separate .{0,60}chair",
    ),
    # A proposal to appoint one person as both chair and chief executive (common wording in India:
    # "Approve Appointment of X as Chairman and Managing Director"). "Vice chairman", an executive
    # chairman who is not the managing director, and items that only set pay are left out.
    (
        "1.3.1",
        "GVG 1.3",
        "MOT",
        "appoint one person as both chairperson and CEO or managing director",
        r"^(approve (the )?(re-?)?(appointment|continuation)|elect|re-?elect|appoint|reappoint)\b.*?(?<!vice )(?<!vice-)(?<!deputy )"
        r"\bchair(man|person|woman)?\b[^;]{0,30}\b(managing director|chief executive|ceo)\b"
        r"|^(approve (the )?(re-?)?(appointment|continuation)|elect|re-?elect|appoint|reappoint)\b.*?"
        r"\b(managing director|chief executive officer|ceo)\b[^;]{0,25}(?<!vice )(?<!vice-)\bchair(man|person|woman)\b",
    ),
    ("3.1.2", "GVG 3.1", "FOR", "declassify the board", r"\bdeclassify"),
    (
        "3.1.5",
        "GVG 3.1",
        "FOR",
        "majority requirements in director elections",
        r"majority vot\w+ (standard )?(for|in) (the )?election of directors",
    ),
    ("3.1.8", "GVG 3.1", "FOR", "proxy access", r"proxy access"),
    ("4.2.2", "GVG 4.2", "FOR", "right to act by written consent", r"act by written consent"),
    (
        "6.2-AT.3",
        "GVG 6.2",
        "FOR",
        "abolish an anti-takeover measure (supermajority requirement)",
        r"simple majority vote|(reduce|eliminate|remove) (the )?supermajority"
        r"|(remove|abolish|eliminate|repeal) .{0,40}(takeover defen[cs]e|poison pill|rights plan)",
    ),
    (
        "3.1.1",
        "GVG 3.1",
        "MOT",
        "classify (stagger) the board",
        r"\bclassify the board|stagger\w* board",
    ),
    (
        "6.2-AT.2",
        "GVG 6.2",
        "MOT",
        "introduce or renew an anti-takeover measure (poison pill)",
        r"poison pill|shareholder rights plan|takeover defen[cs]e",
    ),
    # The guidelines mark 5.2.2 as needing judgement, but the rule names this agenda item itself:
    # "insufficient to make an informed decision, e.g. the agenda item 'other business'".
    (
        "5.2.2",
        "GVG 5.2",
        "MOT",
        'vote on unspecified "other business"',
        r"^(transact )?other business\b",
    ),
]


def match_rule(text):
    """The first clear-cut rule the proposal wording falls under, or None."""
    t = text.lower()
    # 'Require Shareholder Approval of Poison Pill' asks to restrict a pill: that is a different rule.
    if re.search(
        r"(submit|require|subject) .*(poison pill|rights plan).* (to|shareholder) (a )?(shareholder )?(vote|approval)",
        t,
    ):
        return None
    for rule in RULES:
        if re.search(rule[4], t):
            return rule
    return None


def load_scored():
    """Every proposal in the file with the rule it falls under, NBIM's vote by rule, and the monitor's state."""
    rows = bm.read_votes(VOTES)
    bm.add_history_features(rows)  # only for the "same as last time" baseline
    for r in rows:
        rule = match_rule(r["proposal_text"])
        r["rule"] = rule
        r["rule_vote"] = rule[2] if rule else ""
        # The rule gives NBIM's vote. It is "against the board" only when the board recommends the opposite.
        against_board = bool(rule) and r["mgmt_rec"] in ("FOR", "MOT") and rule[2] != r["mgmt_rec"]
        r["rules"] = (
            [
                (
                    rule[1],
                    f"rule {rule[0]}: the proposal asks to {rule[3]}; NBIM's rule says vote {rule[2]}, "
                    f"the board recommends {r['mgmt_rec']}",
                )
            ]
            if against_board
            else []
        )
    run_monitor(rows)
    # Policy watch: a rule NBIM has reworded to "may not" is a judgement call from the day that was seen.
    softer, since = softened_rules()
    for r in rows:
        if r["rules"] and since and r["meeting_date"] >= since and r["rule"][0] in softer:
            r["rule_state"] = {code: "suspended" for code in r["rule_state"]}
    return rows


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
