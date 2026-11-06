"""rules.board: NBIM voting decision support."""

import collections
import re

from src import data as paths
from src.evidence import fetch_board_facts as fb
from src.models import history as bm
from src.rules import directors as dr
from src.rules import policy as pw

VOTES = paths.VOTES
MAX_BOARDS = 5
ON = ("chair", "member")


def val(facts, key):
    return facts[key]["answer"] if facts and key in facts else None


def sure(facts, *keys):
    """True if every fact named has a quote that was found in the proxy."""
    return all(facts[k]["verified"] for k in keys)


def share(part, whole):
    return part / whole if part is not None and whole else None


def is_executive(n):
    """ "yes" only if the proxy does not also call the nominee independent. The reader sometimes
    takes a senior job at another company for a job at this one; a company's own executive is
    never independent, so the independence statement settles it."""
    execu = val(n, "executive")
    return "no" if execu == "yes" and val(n, "independent") == "yes" else execu


def mark_founder(n, company):
    """Set n["founder_here"]: the proxy says the nominee founded THIS company. The reader also says
    "founder" for people who founded some other firm, so the quote must name this company, or say
    "our" or "the Company"."""
    quote = n["founder"]["quote"].lower() if n.get("found") else ""
    first_word = re.sub(r"[^a-z0-9 ]", " ", company.lower()).replace("the ", " ").split()[0]
    n["founder_here"] = (
        bool(n.get("found"))
        and val(n, "founder") == "yes"
        and bool(re.search(r"\bour\b|\bthe company\b", quote) or first_word in quote)
    )


def is_founder(n):
    return n["founder_here"] if "founder_here" in n else val(n, "founder") == "yes"


def decide(n, b):
    """Rules the facts trigger for one nominee. Returns a list of
    (guideline section, reason starting with the rule number, every quote found?)."""
    out = []
    if not n or not n["found"]:
        return out
    indep, execu = val(n, "independent"), is_executive(n)
    board_share = share(val(b, "independent_directors"), val(b, "board_size"))
    audit_share = share(val(b, "audit_committee_independent"), val(b, "audit_committee_members"))
    controlled = val(b, "controlled_company") == "yes"
    need = 1 / 3 if controlled else 0.5
    if indep == "no" and execu == "no" and board_share is not None and board_share < need:
        out.append(
            (
                "GVG 1.1",
                f"rule {'1.1.2' if controlled else '1.1.1'}: not independent and not an executive, and "
                f"{val(b, 'independent_directors'):.0f} of {val(b, 'board_size'):.0f} directors are independent"
                + (" at a controlled company" if controlled else ""),
                sure(n, "independent") and sure(b, "independent_directors"),
            )
        )
    if execu == "yes" and val(n, "pay_committee") in ON:
        out.append(
            (
                "GVG 1.2",
                "rule 1.2.1: an executive of the company who sits on the pay committee",
                sure(n, "executive"),
            )
        )
    if execu == "yes" and val(n, "audit_committee") in ON:
        out.append(
            (
                "GVG 1.2",
                "rule 1.2.2: an executive of the company who sits on the audit committee",
                sure(n, "executive"),
            )
        )
    if indep == "no" and audit_share is not None and audit_share < 0.5:
        out.append(
            (
                "GVG 1.2",
                f"rule 1.2.3: not independent, and {val(b, 'audit_committee_independent'):.0f} of "
                f"{val(b, 'audit_committee_members'):.0f} audit committee members are independent",
                sure(n, "independent") and sure(b, "audit_committee_independent"),
            )
        )
    if val(n, "ceo") == "yes" and val(n, "board_chair") == "yes" and not is_founder(n):
        out.append(
            (
                "GVG 1.3",
                "rule 1.3.1: the proxy names this nominee as both chair of the board and CEO",
                sure(n, "ceo", "board_chair"),
            )
        )
    others = val(n, "other_public_boards")
    if others is not None and len(others) + 1 > MAX_BOARDS:
        out.append(
            (
                "GVG 2.1",
                f"rule 2.1.1: sits on {len(others)} other listed company boards besides this one "
                f"({', '.join(others)})",
                sure(n, "other_public_boards"),
            )
        )
    if val(n, "attended_under_75_pct") == "yes":
        out.append(
            (
                "GVG 2.1",
                "rule 2.1.2: attended fewer than 75 percent of meetings",
                sure(n, "attended_under_75_pct"),
            )
        )
    women, size = val(b, "women_directors"), val(b, "board_size")
    if (
        val(n, "nomination_committee") == "chair"
        and women is not None
        and size
        and min(women, size - women) < 2
    ):
        out.append(
            (
                "GVG 2.3",
                f"rule 2.3.1: chairs the nomination committee, and the board of {size:.0f} has "
                f"{women:.0f} women",
                b["women_directors"]["verified"],
            )
        )
    return out


def count_women(board, nominees):
    """Fill in the number of women when the proxy does not state it but every director is on the ballot:
    then it is the number of nominees the proxy refers to as women. Marked as found, since it is a count
    of the nominees, and only used when each nominee's gender is known."""
    size = val(board, "board_size")
    if (
        val(board, "women_directors") is None
        and val(board, "classified_board") == "no"
        and size == len(nominees)
    ):
        genders = [val(n, "gender") for n in nominees]
        if all(g in ("female", "male") for g in genders):
            board["women_directors"] = {
                "answer": float(genders.count("female")),
                "quote": "counted from the nominees",
                "verified": True,
            }


def judgement_notes(n, b, opposed_pay_before):
    """Facts that matter for rules the guidelines say need judgement. Shown to the reviewer, never automatic."""
    out = []
    if not n or not n["found"]:
        return out
    support = val(b, "prior_pay_support_pct")
    if val(n, "pay_committee") in ON and support is not None and support < 70:
        out.append(
            (
                "GVG 3.2",
                f"rule 3.2.2 (judgement): on the pay committee, and the last pay vote had {support:.0f}% support",
                "pay committee member, last pay vote under 70% support",
            )
        )
    if val(n, "ceo") == "yes" and val(n, "board_chair") == "yes" and is_founder(n):
        out.append(
            (
                "GVG 1.3",
                "rule 1.3.1 (judgement): chair and CEO, and the proxy says the nominee founded the company; "
                "the guidelines allow this for a limited period",
                "chair and CEO who founded the company",
            )
        )
    others = val(n, "other_public_boards")
    if others is not None and val(n, "executive_elsewhere") == "yes" and len(others) >= 2:
        out.append(
            (
                "GVG 2.1",
                f"rule 2.1.1 (judgement): a full-time executive at another company who also sits on "
                f"{len(others)} other listed boards",
                "executive elsewhere with two or more other listed boards",
            )
        )
    if val(n, "board_chair") == "yes" and val(n, "chairs_other_board") == "yes":
        out.append(
            (
                "GVG 2.1",
                "rule 2.1.1 (judgement): chairs this board and the board of another company",
                "chairs this board and another company's board",
            )
        )
    if val(n, "pay_committee") in ON and opposed_pay_before:
        out.append(
            (
                "GVG 3.2",
                "rule 3.2.2 (judgement): on the pay committee, and NBIM voted against this company's pay at the previous meeting",
                "pay committee member, NBIM opposed pay at the previous meeting",
            )
        )
    if val(n, "nomination_committee") in ON and val(b, "majority_proposal_not_acted_on") == "yes":
        out.append(
            (
                "GVG 3.2",
                "rule 3.2.1 (judgement): on the nomination committee, and a majority-supported shareholder proposal was not acted on",
                "nomination committee member, majority-supported proposal not acted on",
            )
        )
    if val(b, "classified_board") == "yes":
        out.append(
            (
                "GVG 3.1",
                "rule 3.1.3 (judgement): the board is classified, so directors serve terms longer than one year",
                "nominee to a classified board",
            )
        )
    return out


TRUST_AFTER = 2  # a signal acts alone once NBIM has followed it at this many meetings in a row
RULE_FACTS = {  # the facts each signal rests on: (nominee or board, key). Their quotes are shown with the decision.
    "1.1.1": (("n", "independent"), ("b", "independent_directors")),
    "1.1.2": (("n", "independent"), ("b", "independent_directors")),
    "1.2.1": (("n", "executive"),),
    "1.2.2": (("n", "executive"),),
    "1.2.3": (("n", "independent"), ("b", "audit_committee_independent")),
    "1.3.1": (("n", "ceo"), ("n", "board_chair")),
    "1.3.1 founder": (("n", "ceo"), ("n", "board_chair"), ("n", "founder")),
    "2.1.1": (),
    "2.1.1 two chairs": (("n", "board_chair"),),
    "2.1.2": (("n", "attended_under_75_pct"),),
    "2.3.1": (("b", "women_directors"),),
}
OWN_READING = {  # facts the guidelines name but leave to judgement; they can earn trust like a rule
    "chair and CEO who founded the company": "1.3.1 founder",
    "chairs this board and another company's board": "2.1.1 two chairs",
}


def signals_for(r):
    """Everything that fired for one nominee, from both sources, as dicts:
    name (rule and source), section, text, quoted (the facts have a quote found in the proxy)."""
    out = [
        {"name": rule_id(t) + " (proxy)", "section": c, "text": t, "quoted": q}
        for c, t, q in r["all_rules"]
    ]
    out += [
        {"name": OWN_READING[lab] + " (proxy)", "section": c, "text": t, "quoted": True}
        for c, t, lab in r["notes"]
        if lab in OWN_READING
    ]
    out += [
        {"name": rule_id(t) + " (SEC filings)", "section": c, "text": t, "quoted": True}
        for c, t in r["sec_rules"]
    ]
    return out


def earn_trust(rows, trust_after=TRUST_AFTER):
    """Decide, meeting by meeting in date order, which signals the tool may act on alone.

    A signal is trusted at a meeting if NBIM followed it at each of the last
    `trust_after` earlier meetings where it fired (it voted against at least
    half of the nominees the signal pointed at). Every signal starts untrusted,
    one miss takes the trust away, and meetings on the same date do not see
    each other. Only earlier votes are used, which NBIM itself would know.
    """
    past = collections.defaultdict(
        list
    )  # signal name -> outcomes at earlier meetings, oldest first
    by_date = collections.defaultdict(list)
    for r in rows:
        by_date[r["meeting_date"]].append(r)
    for date in sorted(by_date):
        today = collections.defaultdict(
            lambda: collections.defaultdict(list)
        )  # name -> company -> outcomes
        for r in by_date[date]:
            for sig in r["signals"]:
                history = past[sig["name"]]
                sig["trusted"] = len(history) >= trust_after and all(history[-trust_after:])
                sig["record"] = f"{sum(history)} of {len(history)}"
                today[sig["name"]][r["company_id"]].append(r["y"])
        for name, companies in today.items():
            for votes in companies.values():
                past[name].append(1 if 2 * sum(votes) >= len(votes) else 0)


def load_scored():
    """Every US director nominee in NBIM's file with the reader's facts, the signals they trigger
    and whether each signal has earned trust. For the prediction pipeline: r["rules"] lists (section, text) and
    r["rule_state"] says per section whether the tool may act alone ("active") or not ("suspended")."""
    rows = dr.load_scored()  # brings the SEC-role facts and rules along as r["f"], r["rules"]
    cache = fb.load_cache()
    by_name, alerts = {}, {}
    for (company, date), rec in cache.items():
        # A proxy that speaks to an automated reader (checked when it was read): its facts are shown,
        # and a person decides.
        alerts[(company, date)] = rec.get("reader_alert", "")
        count_women(rec["answers"]["board"], rec["answers"]["nominees"])
        for n in rec["answers"]["nominees"]:
            mark_founder(n, rec["company"])
            by_name[(company, date, n["ballot_name"])] = (n, rec["answers"]["board"], rec["proxy"])
    # NBIM's own pay votes at earlier meetings of the same company (from the same file, earlier dates only).
    pay = collections.defaultdict(list)
    for r in bm.read_votes(VOTES):
        if r["proposal_type"] == "SAY_ON_PAY":
            pay[r["company_id"]].append((r["meeting_date"], r["y"]))
    for r in rows:
        r["sec_rules"], r["sec_state"] = r["rules"], r["rule_state"]
        n, b, proxy = by_name.get(
            (r["company_id"], r["meeting_date"], dr.nominee_name(r["proposal_text"]).strip()),
            (None, None, None),
        )
        earlier = sorted(p for p in pay[r["company_id"]] if p[0] < r["meeting_date"])
        r["n"], r["b"], r["proxy"] = n, b, proxy
        r["proxy_alert"] = alerts.get((r["company_id"], r["meeting_date"]), "")
        r["all_rules"] = decide(n, b)
        r["notes"] = judgement_notes(n, b, bool(earlier) and earlier[-1][1] == 1)
        r["signals"] = signals_for(r)
    earn_trust(rows)
    # Policy watch: a rule NBIM has reworded from "will not" to "may not" on its website is a judgement
    # call from the day that was seen. No meeting in the file is that late, so no test is affected.
    softer, since = pw.softened_rules()
    for r in rows:
        for g in r["signals"]:
            if since and r["meeting_date"] >= since and g["name"].split(" ")[0] in softer:
                g["trusted"] = False
                g["record"] += "; NBIM has since reworded this rule to 'may not'"
    for r in rows:
        for g in r["signals"]:
            g["quotes"] = []
            if "(proxy)" in g["name"]:
                facts = {"n": r["n"], "b": r["b"]}
                g["quotes"] = [
                    facts[w][k]["quote"]
                    for w, k in RULE_FACTS[g["name"].replace(" (proxy)", "")]
                    if facts[w][k]["verified"]
                    and facts[w][k]["quote"]
                    and "counted from" not in facts[w][k]["quote"]
                ]
        r["acts_alone"] = [g for g in r["signals"] if g["trusted"] and g["quoted"]]

        def say(g):
            return g["text"] + (
                ' (proxy: "' + '"; "'.join(g["quotes"]) + '")' if g["quotes"] else ""
            )

        r["rules"] = list(dict.fromkeys((g["section"], say(g)) for g in r["signals"]))
        held = [g for g in r["signals"] if g not in r["acts_alone"]]
        r["hold_reason"] = "; ".join(
            f"{g['name']}: "
            + (
                "the quote for this fact was not found in the proxy"
                if not g["quoted"]
                else f"NBIM followed this at {g['record']} earlier meetings, and not at the last {TRUST_AFTER} in a row"
            )
            for g in held
        )
        r["rule_state"] = {g["section"]: "suspended" for g in r["signals"]}
        r["rule_state"].update({g["section"]: "active" for g in r["acts_alone"]})
        r["evidence_url"] = (
            (r["proxy"] or {}).get("url", "")
            if any("(proxy)" in g["name"] for g in r["signals"])
            else ""
        )
    return rows


def rule_id(text):
    return text.split(":")[0].replace("rule ", "").replace(" (judgement)", "")
