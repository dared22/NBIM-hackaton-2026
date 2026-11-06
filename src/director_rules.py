"""NBIM's written director rules, applied in code to facts filed before the meeting.

Same design as main's board_rules.py: facts are read from filings, the rules are plain code, and a
rule only decides a vote on its own once NBIM's own earlier votes show it is still practice.

Rules (the guideline's own numbers; a rule is used only if it is in the edition in force)
    US, from the proxy (main's AI reading, each fact with a quote checked against the text)
      1.1.1  non-executive, non-independent nominee; board less than half independent
      1.1.2  the same at a controlled company, with a third as the limit
      1.2.1  an executive on the pay committee
      1.2.2  an executive on the audit committee
      1.2.3  non-independent nominee; audit committee less than half independent
      1.3.1  chair who is also the CEO. Founders are the guidelines' stated exception: they go to a person
      2.1.1  more than five boards (this one and five or more other listed companies)
      2.1.2  attended fewer than 75 percent of meetings
      2.3.1  chair of the nomination committee when the board lacks one (2020 edition) or two (2023-)
             members of each gender
    Japan, from the EDINET annual report
      1.1.1  outside, non-independent nominee; board less than half independent

Trust (as in main): a rule decides alone only when NBIM followed it at the last TRUST_AFTER earlier
meetings where it fired (MOT on at least half of the nominees it pointed at). Every rule starts
untrusted, one miss removes the trust, and meetings on the same date do not see each other. Until a
rule is trusted, or when its facts lack a verified quote, the proposal goes to a person with the fact.
TRUST_AFTER is main's untuned choice. The rules were chosen from the guideline text and from main,
whose choice was made after looking at all years; this is said in the report.
"""

from collections import defaultdict

TRUST_AFTER = 2
MAX_BOARDS = 5
ON = ("chair", "member")
VOTED = ("FOR", "MOT", "AVSTÅ")


def _num(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _verified(row, *fields):
    return all(row.get(f"{f}_verified") == "1" for f in fields)


def _executive(n):
    """'yes' only if the proxy does not also call the nominee independent (main's correction)."""
    return "no" if n["executive"] == "yes" and n["independent"] == "yes" else n["executive"]


def _other_boards(n):
    return [b.strip() for b in (n.get("other_public_boards") or "").split(";") if b.strip()]


def us_rules(n, b, rule_ids, rule_texts):
    """(rule id, fact, quoted) for one US nominee."""
    out = []
    indep, execu = n["independent"], _executive(n)
    size, independent = _num(b.get("board_size")), _num(b.get("independent_directors"))
    controlled = b.get("controlled_company") == "yes"
    if indep == "no" and execu == "no" and size and independent is not None:
        limit, rule = (1 / 3, "1.1.2") if controlled else (0.5, "1.1.1")
        if independent / size < limit:
            out.append((rule, f"not independent and not an executive, and {independent:.0f} of {size:.0f} directors are "
                              f"independent" + (" at a controlled company" if controlled else ""),
                        _verified(n, "independent") and _verified(b, "independent_directors")))
    if execu == "yes" and n.get("pay_committee") in ON:
        out.append(("1.2.1", "an executive of the company who sits on the pay committee", _verified(n, "executive")))
    if execu == "yes" and n.get("audit_committee") in ON:
        out.append(("1.2.2", "an executive of the company who sits on the audit committee", _verified(n, "executive")))
    members, audit_indep = _num(b.get("audit_committee_members")), _num(b.get("audit_committee_independent"))
    if indep == "no" and members and audit_indep is not None and audit_indep / members < 0.5:
        out.append(("1.2.3", f"not independent, and {audit_indep:.0f} of {members:.0f} audit committee members are independent",
                    _verified(n, "independent") and _verified(b, "audit_committee_independent")))
    if n["ceo"] == "yes" and n["board_chair"] == "yes":
        founder = n.get("founder") == "yes" and _verified(n, "founder")
        out.append(("1.3.1", "the proxy names this nominee as both chair of the board and CEO"
                    + (" (a founder: the guidelines allow this for a limited period, so a person decides)" if founder else ""),
                    _verified(n, "ceo", "board_chair") and not founder))
    others = _other_boards(n)
    if len(others) + 1 > MAX_BOARDS:
        out.append(("2.1.1", f"sits on {len(others)} other listed company boards besides this one", _verified(n, "other_public_boards")))
    if n.get("attended_under_75_pct") == "yes":
        out.append(("2.1.2", "attended fewer than 75 percent of board meetings", _verified(n, "attended_under_75_pct")))
    women = _num(b.get("women_directors"))
    if n.get("nomination_committee") == "chair" and women is not None and size and "2.3.1" in rule_ids:
        need = 2 if "at least two" in rule_texts.get("2.3.1", "") else 1
        if min(women, size - women) < need:
            out.append(("2.3.1", f"chairs the nomination committee, and the board of {size:.0f} has {women:.0f} women",
                        _verified(b, "women_directors")))
    return [x for x in out if x[0] in rule_ids]


def japan_rules(jp, rule_ids):
    if not jp or not jp.get("found") or not jp.get("nominee_found"):
        return []
    if jp["nominee_outside"] and not jp["nominee_independent"] and jp["independent_share"] < 0.5 and "1.1.1" in rule_ids:
        # EDINET is a filing, not a reading: the facts count as quoted.
        return [("1.1.1", f"outside but not independent, and {jp['independent']} of {jp['board_size']} directors are "
                          f"independent (EDINET report {jp['report_doc_id']})", True)]
    return []


def fired(row, known, by_section):
    """Every rule the facts trigger for this proposal: [(rule id, fact, quoted, source)]."""
    if row["proposal_type"] != "DIRECTOR_ELECTION":
        return []
    rules = {r["id"]: r["tekst"] for section in by_section.values() for r in section}
    us = known.us_director(row)
    if us and us["found"]:
        return [(rule, fact, quoted, "US proxy") for rule, fact, quoted in us_rules(us["nominee_row"], us["board_row"], set(rules), rules)]
    return [(rule, fact, quoted, "Japan EDINET") for rule, fact, quoted in japan_rules(known.japan.for_row(row), set(rules))]


def rule_states(rows, known, guidelines_for, versions, extra=()):
    """For every proposal where a rule fires: [(rule id, fact, quoted, source, trusted, record)].

    rows: proposals with NBIM's votes, in any order. extra: proposals without votes (a pasted agenda),
    scored against all earlier votes. Only votes from earlier dates are used.
    """
    cases, new = [], {id(r) for r in extra}
    for r in list(rows) + list(extra):
        if r["proposal_type"] != "DIRECTOR_ELECTION" or (id(r) not in new and r["nbim_vote"] not in VOTED):
            continue
        _, by_section = guidelines_for(r["meeting_date"], versions)
        signals = fired(r, known, by_section)
        if signals:
            cases.append((r, signals))
    cases.sort(key=lambda c: c[0]["meeting_date"])
    past = defaultdict(list)  # (rule, source) -> outcome at each earlier meeting where it fired, oldest first
    states = {}
    i = 0
    while i < len(cases):
        date = cases[i][0]["meeting_date"]
        today = defaultdict(lambda: defaultdict(list))  # (rule, source) -> meeting -> NBIM voted MOT?
        while i < len(cases) and cases[i][0]["meeting_date"] == date:
            r, signals = cases[i]
            out = []
            for rule, fact, quoted, source in signals:
                history = past[(rule, source)]
                trusted = len(history) >= TRUST_AFTER and all(history[-TRUST_AFTER:])
                out.append((rule, fact, quoted, source, trusted, f"{sum(history)} of {len(history)}"))
                if r["nbim_vote"] in VOTED:
                    today[(rule, source)][r["meeting_id"]].append(r["nbim_vote"] == "MOT")
            states[(r["meeting_id"], r["item_no"])] = out
            i += 1
        for key, meetings in today.items():
            for votes in meetings.values():
                past[key].append(2 * sum(votes) >= len(votes))
    return states


def deciding_rule(signals):
    """The rule that decides the vote alone (trusted, with verified facts), or None."""
    return next((rule for rule, _, quoted, _, trusted, _ in signals if quoted and trusted), None)


def describe(signals):
    """Plain sentences for the explanation: every rule that fired, and whether it decided."""
    out = []
    for rule, fact, quoted, source, trusted, record in signals:
        if quoted and trusted:
            status = f"decides the vote: NBIM followed it at the last {TRUST_AFTER} meetings where it applied ({record} so far)"
        elif not quoted:
            status = "a person decides: the fact has no quote found in the filing"
        else:
            status = f"a person decides: NBIM followed it at {record} earlier meetings, not the last {TRUST_AFTER} in a row"
        out.append(f"rule {rule} applies ({source}): {fact}; {status}")
    return out


def needs_person(signals):
    return bool(signals) and deciding_rule(signals) is None
