"""US director elections: NBIM's written rules applied to facts read from the proxy.

Run from the repo root (no internet, no API key; the reader's answers are cached):
    python3 src/agent/board_rules.py

Two steps, kept apart on purpose
    1. An AI model reads each company's proxy and records facts, each with a
       quote that is checked against the text (fetch_board_facts.py). It never
       sees NBIM's rules or votes.
    2. This script applies NBIM's rules to those facts in plain code. The same
       facts always give the same answer, and each answer names its rule.

No training, so every year in the file is a test year. The 2025 guidelines are
applied to all years.

Rules applied (the guideline's own numbers)
    1.1.1  non-executive, non-independent nominee on a board that is less than
           half independent (1.1.2: less than a third at a controlled company)
    1.2.1  an executive on the pay committee
    1.2.2  an executive on the audit committee
    1.2.3  non-independent nominee when the audit committee is less than half independent
    1.3.1  a chair who is also the CEO. The guidelines make an exception for
           founders ("we may support this for a limited period"), so a founder
           goes to a person
    2.1.1  more than five boards (this one and five or more other listed companies)
    2.1.2  attended fewer than 75 percent of meetings
    2.3.1  chair of the nomination committee when the board has fewer than two
           members of either gender

Shown but not used for suggestions (the guidelines say these need judgement)
    3.2.2  pay committee members after low support for pay
    3.2.1  nomination committee members after a majority-supported proposal was not acted on
    3.1.3  nominees to a classified board
    link to the pay vote: pay committee members at a company where NBIM
    opposed pay at the previous meeting

Assumptions, stated up front
    - "Developed market, large or mid cap" is assumed for every US company in the file.
    - "Independent" is the company's own statement in the proxy.
    - A rule fires on its own only if the facts it rests on have a quote that
      was found in the proxy. Otherwise it is listed as "quote not found" and
      goes to a person.

When the tool acts on its own
    The 2025 guidelines are applied to all years, and NBIM's practice is not
    always its written rule: some rules were not yet practice in 2019 (two
    women on the board), one stopped being practice in 2026 (chair and CEO),
    and some are applied with exceptions (attendance). So every signal has to
    earn trust: the tool suggests "against" on its own only when NBIM followed
    that signal at the last two meetings where it fired. Until then, and after
    any miss, the nominee goes to a person with the fact and its quote. The
    trust rule only uses NBIM's votes at earlier meetings.

    Two facts the guidelines name but leave to judgement can earn trust the
    same way: a founder who is chair and CEO (section 1.3), and a chair who
    also chairs another company's board (rule 2.1.1 and the position paper on
    time commitment). The other judgement facts are shown to the reviewer only.

Honest note: which facts to ask for, and which judgement facts may earn trust,
was decided after looking at all years of this file, 2026 included. The trust
rule itself (two meetings in a row) was not tuned.

Answer key: data/dirty/real_votes.csv. The rule decisions use no votes. The
trust rule and the scoring do.
"""

import collections
import csv
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "src", "agent"))
from benchmark import model as bm  # noqa: E402
import director_rules as dr  # noqa: E402
import fetch_board_facts as fb  # noqa: E402

VOTES = os.path.join(ROOT, "data", "dirty", "real_votes.csv")
OUT = os.path.join(ROOT, "data", "outputs", "board_rules.csv")
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
    """"yes" only if the proxy does not also call the nominee independent. The reader sometimes
    takes a senior job at another company for a job at this one; a company's own executive is
    never independent, so the independence statement settles it."""
    execu = val(n, "executive")
    return "no" if execu == "yes" and val(n, "independent") == "yes" else execu


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
        out.append(("GVG 1.1", f"rule {'1.1.2' if controlled else '1.1.1'}: not independent and not an executive, and "
                    f"{val(b, 'independent_directors'):.0f} of {val(b, 'board_size'):.0f} directors are independent"
                    + (" at a controlled company" if controlled else ""),
                    sure(n, "independent") and sure(b, "independent_directors")))
    if execu == "yes" and val(n, "pay_committee") in ON:
        out.append(("GVG 1.2", "rule 1.2.1: an executive of the company who sits on the pay committee", sure(n, "executive")))
    if execu == "yes" and val(n, "audit_committee") in ON:
        out.append(("GVG 1.2", "rule 1.2.2: an executive of the company who sits on the audit committee", sure(n, "executive")))
    if indep == "no" and audit_share is not None and audit_share < 0.5:
        out.append(("GVG 1.2", f"rule 1.2.3: not independent, and {val(b, 'audit_committee_independent'):.0f} of "
                    f"{val(b, 'audit_committee_members'):.0f} audit committee members are independent",
                    sure(n, "independent") and sure(b, "audit_committee_independent")))
    if val(n, "ceo") == "yes" and val(n, "board_chair") == "yes" and val(n, "founder") != "yes":
        out.append(("GVG 1.3", "rule 1.3.1: the proxy names this nominee as both chair of the board and CEO",
                    sure(n, "ceo", "board_chair")))
    others = val(n, "other_public_boards")
    if others is not None and len(others) + 1 > MAX_BOARDS:
        out.append(("GVG 2.1", f"rule 2.1.1: sits on {len(others)} other listed company boards besides this one "
                    f"({', '.join(others)})", sure(n, "other_public_boards")))
    if val(n, "attended_under_75_pct") == "yes":
        out.append(("GVG 2.1", "rule 2.1.2: attended fewer than 75 percent of meetings", sure(n, "attended_under_75_pct")))
    women, size = val(b, "women_directors"), val(b, "board_size")
    if val(n, "nomination_committee") == "chair" and women is not None and size and min(women, size - women) < 2:
        out.append(("GVG 2.3", f"rule 2.3.1: chairs the nomination committee, and the board of {size:.0f} has "
                    f"{women:.0f} women", b["women_directors"]["verified"]))
    return out


def count_women(board, nominees):
    """Fill in the number of women when the proxy does not state it but every director is on the ballot:
    then it is the number of nominees the proxy refers to as women. Marked as found, since it is a count
    of the nominees, and only used when each nominee's gender is known."""
    size = val(board, "board_size")
    if val(board, "women_directors") is None and val(board, "classified_board") == "no" and size == len(nominees):
        genders = [val(n, "gender") for n in nominees]
        if all(g in ("female", "male") for g in genders):
            board["women_directors"] = {"answer": float(genders.count("female")), "quote": "counted from the nominees", "verified": True}


def judgement_notes(n, b, opposed_pay_before):
    """Facts that matter for rules the guidelines say need judgement. Shown to the reviewer, never automatic."""
    out = []
    if not n or not n["found"]:
        return out
    support = val(b, "prior_pay_support_pct")
    if val(n, "pay_committee") in ON and support is not None and support < 70:
        out.append(("GVG 3.2", f"rule 3.2.2 (judgement): on the pay committee, and the last pay vote had {support:.0f}% support",
                    "pay committee member, last pay vote under 70% support"))
    if val(n, "ceo") == "yes" and val(n, "board_chair") == "yes" and val(n, "founder") == "yes":
        out.append(("GVG 1.3", "rule 1.3.1 (judgement): chair and CEO, and the proxy says the nominee founded the company; "
                    "the guidelines allow this for a limited period",
                    "chair and CEO who founded the company"))
    others = val(n, "other_public_boards")
    if others is not None and val(n, "executive_elsewhere") == "yes" and len(others) >= 2:
        out.append(("GVG 2.1", f"rule 2.1.1 (judgement): a full-time executive at another company who also sits on "
                    f"{len(others)} other listed boards",
                    "executive elsewhere with two or more other listed boards"))
    if val(n, "board_chair") == "yes" and val(n, "chairs_other_board") == "yes":
        out.append(("GVG 2.1", "rule 2.1.1 (judgement): chairs this board and the board of another company",
                    "chairs this board and another company's board"))
    if val(n, "pay_committee") in ON and opposed_pay_before:
        out.append(("GVG 3.2", "rule 3.2.2 (judgement): on the pay committee, and NBIM voted against this company's pay at the previous meeting",
                    "pay committee member, NBIM opposed pay at the previous meeting"))
    if val(n, "nomination_committee") in ON and val(b, "majority_proposal_not_acted_on") == "yes":
        out.append(("GVG 3.2", "rule 3.2.1 (judgement): on the nomination committee, and a majority-supported shareholder proposal was not acted on",
                    "nomination committee member, majority-supported proposal not acted on"))
    if val(b, "classified_board") == "yes":
        out.append(("GVG 3.1", "rule 3.1.3 (judgement): the board is classified, so directors serve terms longer than one year",
                    "nominee to a classified board"))
    return out


TRUST_AFTER = 2      # a signal acts alone once NBIM has followed it at this many meetings in a row
RULE_FACTS = {       # the facts each signal rests on: (nominee or board, key). Their quotes are shown with the decision.
    "1.1.1": (("n", "independent"), ("b", "independent_directors")), "1.1.2": (("n", "independent"), ("b", "independent_directors")),
    "1.2.1": (("n", "executive"),), "1.2.2": (("n", "executive"),),
    "1.2.3": (("n", "independent"), ("b", "audit_committee_independent")),
    "1.3.1": (("n", "ceo"), ("n", "board_chair")), "1.3.1 founder": (("n", "ceo"), ("n", "board_chair"), ("n", "founder")),
    "2.1.1": (), "2.1.1 two chairs": (("n", "board_chair"),), "2.1.2": (("n", "attended_under_75_pct"),),
    "2.3.1": (("b", "women_directors"),),
}
OWN_READING = {      # facts the guidelines name but leave to judgement; they can earn trust like a rule
    "chair and CEO who founded the company": "1.3.1 founder",
    "chairs this board and another company's board": "2.1.1 two chairs",
}


def signals_for(r):
    """Everything that fired for one nominee, from both sources, as dicts:
    name (rule and source), section, text, quoted (the facts have a quote found in the proxy)."""
    out = [{"name": rule_id(t) + " (proxy)", "section": c, "text": t, "quoted": q} for c, t, q in r["all_rules"]]
    out += [{"name": OWN_READING[lab] + " (proxy)", "section": c, "text": t, "quoted": True}
            for c, t, lab in r["notes"] if lab in OWN_READING]
    out += [{"name": rule_id(t) + " (SEC filings)", "section": c, "text": t, "quoted": True} for c, t in r["sec_rules"]]
    return out


def earn_trust(rows, trust_after=TRUST_AFTER):
    """Decide, meeting by meeting in date order, which signals the tool may act on alone.

    A signal is trusted at a meeting if NBIM followed it at each of the last
    `trust_after` earlier meetings where it fired (it voted against at least
    half of the nominees the signal pointed at). Every signal starts untrusted,
    one miss takes the trust away, and meetings on the same date do not see
    each other. Only earlier votes are used, which NBIM itself would know.
    """
    past = collections.defaultdict(list)            # signal name -> outcomes at earlier meetings, oldest first
    by_date = collections.defaultdict(list)
    for r in rows:
        by_date[r["meeting_date"]].append(r)
    for date in sorted(by_date):
        today = collections.defaultdict(lambda: collections.defaultdict(list))   # name -> company -> outcomes
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
    and whether each signal has earned trust. For src/run.py: r["rules"] lists (section, text) and
    r["rule_state"] says per section whether the tool may act alone ("active") or not ("suspended")."""
    rows = dr.load_scored()          # brings the SEC-role facts and rules along as r["f"], r["rules"]
    cache = fb.load_cache()
    by_name = {}
    for (company, date), rec in cache.items():
        count_women(rec["answers"]["board"], rec["answers"]["nominees"])
        for n in rec["answers"]["nominees"]:
            by_name[(company, date, n["ballot_name"])] = (n, rec["answers"]["board"], rec["proxy"])
    # NBIM's own pay votes at earlier meetings of the same company (from the same file, earlier dates only).
    pay = collections.defaultdict(list)
    for r in bm.read_votes(VOTES):
        if r["proposal_type"] == "SAY_ON_PAY":
            pay[r["company_id"]].append((r["meeting_date"], r["y"]))
    for r in rows:
        r["sec_rules"], r["sec_state"] = r["rules"], r["rule_state"]
        n, b, proxy = by_name.get((r["company_id"], r["meeting_date"], dr.nominee_name(r["proposal_text"]).strip()), (None, None, None))
        earlier = sorted(p for p in pay[r["company_id"]] if p[0] < r["meeting_date"])
        r["n"], r["b"], r["proxy"] = n, b, proxy
        r["all_rules"] = decide(n, b)
        r["notes"] = judgement_notes(n, b, bool(earlier) and earlier[-1][1] == 1)
        r["signals"] = signals_for(r)
    earn_trust(rows)
    for r in rows:
        for g in r["signals"]:
            g["quotes"] = []
            if "(proxy)" in g["name"]:
                facts = {"n": r["n"], "b": r["b"]}
                g["quotes"] = [facts[w][k]["quote"] for w, k in RULE_FACTS[g["name"].replace(" (proxy)", "")]
                               if facts[w][k]["verified"] and facts[w][k]["quote"] and "counted from" not in facts[w][k]["quote"]]
        r["acts_alone"] = [g for g in r["signals"] if g["trusted"] and g["quoted"]]
        say = lambda g: g["text"] + (" (proxy: \"" + "\"; \"".join(g["quotes"]) + "\")" if g["quotes"] else "")
        r["rules"] = list(dict.fromkeys((g["section"], say(g)) for g in r["signals"]))
        held = [g for g in r["signals"] if g not in r["acts_alone"]]
        r["hold_reason"] = "; ".join(
            f"{g['name']}: " + ("the quote for this fact was not found in the proxy" if not g["quoted"] else
            f"NBIM followed this at {g['record']} earlier meetings, and not at the last {TRUST_AFTER} in a row") for g in held)
        r["rule_state"] = {g["section"]: "suspended" for g in r["signals"]}
        r["rule_state"].update({g["section"]: "active" for g in r["acts_alone"]})
        r["evidence_url"] = (r["proxy"] or {}).get("url", "") if any("(proxy)" in g["name"] for g in r["signals"]) else ""
    return rows


def rule_id(text):
    return text.split(":")[0].replace("rule ", "").replace(" (judgement)", "")


def line(label, flagged, against_total):
    hits = sum(r["y"] for r in flagged)
    return [label, len(flagged), hits, len(flagged) - hits, f"{hits / len(flagged):.0%}" if flagged else "-",
            f"{hits / against_total:.0%}"]


def main():
    rows = load_scored()
    read = [r for r in rows if r["n"]]
    found = [r for r in read if r["n"]["found"]]
    against = [r for r in rows if r["y"]]
    C = collections.Counter
    print(f"US director nominees in NBIM's file: {len(rows)}, {len(against)} against the board, "
          f"{rows[0]['meeting_date'][:4]}-{rows[-1]['meeting_date'][:4]}")
    print(f"Proxy read for {len(read)} of them ({len(read) / len(rows):.0%}); the nominee was found in the proxy for {len(found)}.\n")

    print("1. How much did the reader find, and was the quote in the text?")
    out = []
    for key in ("independent", "executive", "ceo", "board_chair", "executive_elsewhere", "other_public_boards"):
        known = [r for r in found if val(r["n"], key) not in ("unknown", None)]
        out.append([key, len(known), f"{len(known) / len(found):.0%}", sum(r["n"][key]["verified"] for r in known)])
    for key in ("audit_committee", "pay_committee", "nomination_committee", "gender"):
        known = [r for r in found if val(r["n"], key) not in ("unknown", None)]
        out.append([key, len(known), f"{len(known) / len(found):.0%}", "from a table"])
    bm.table(["Fact about the nominee", "Answered", "Share", "of which with a quote found"], out)

    print("\n2. Two sources, one question: chair and CEO, from the proxy and from SEC insider filings")
    both = [r for r in found if r["f"] and r["f"]["matched"]]
    cell = C((val(r["n"], "ceo") == "yes" and val(r["n"], "board_chair") == "yes", bool(r["f"]["chair_ceo"])) for r in both)
    bm.table(["", "SEC filings: chair and CEO", "SEC filings: not"],
             [["Proxy: chair and CEO", cell[(True, True)], cell[(True, False)]],
              ["Proxy: not", cell[(False, True)], cell[(False, False)]]])
    agree = cell[(True, True)] + cell[(False, False)]
    print(f"   The two sources agree on {agree} of {len(both)} nominees ({agree / len(both):.1%}).")
    cell = C((is_executive(r["n"]) == "yes", bool(r["f"]["executive"])) for r in both)
    agree = cell[(True, True)] + cell[(False, False)]
    print(f"   On 'is an executive of this company' they agree on {agree} of {len(both)} ({agree / len(both):.1%}): "
          f"both yes {cell[(True, True)]}, proxy only {cell[(True, False)]}, SEC filings only {cell[(False, True)]}.")

    print("\n3. Each rule on its own, all years (no training)")
    out = []
    names = sorted({rule_id(t) for r in rows for _, t, _ in r["all_rules"]})
    for name in names:
        hit = [r for r in rows if any(rule_id(t) == name for _, t, _ in r["all_rules"])]
        quoted = [r for r in hit if any(rule_id(t) == name and q for _, t, q in r["all_rules"])]
        cited = sum(1 for r in hit if r["y"] and r["rationale_section"] == next(c for c, t, _ in r["all_rules"] if rule_id(t) == name))
        out.append([name, len(hit), sum(r["y"] for r in hit), f"{sum(r['y'] for r in hit) / len(hit):.0%}",
                    f"{sum(r['y'] for r in quoted)}/{len(quoted)}", cited])
    bm.table(["Rule", "Fires", "NBIM against", "Share", "With every quote found: against/fires", "NBIM named the same section"], out)
    print(f"   For comparison, NBIM votes against {len(against) / len(rows):.1%} of all US director nominees.")

    print("\n4. Facts for rules that the guidelines say need judgement")
    out = []
    for label in sorted({label for r in rows for _, _, label in r["notes"]}):
        hit = [r for r in rows if any(lab == label for _, _, lab in r["notes"])]
        rid = next(rule_id(t) for r in hit for _, t, lab in r["notes"] if lab == label)
        out.append([rid, label, len(hit), sum(r["y"] for r in hit), f"{sum(r['y'] for r in hit) / len(hit):.0%}"])
    bm.table(["Rule", "Fact", "Nominees", "NBIM against", "Share"], out)
    print("   The first two can earn trust like a rule (section 5). The others are shown to the reviewer only.")

    print("\n5. Every signal from both sources, all years: how often NBIM voted against when it fired")
    names = sorted({g["name"] for r in rows for g in r["signals"]})
    out = []
    for name in names:
        hit = [r for r in rows if any(g["name"] == name for g in r["signals"])]
        alone = [r for r in hit if any(g["name"] == name and g["trusted"] and g["quoted"] for g in r["signals"])]
        out.append([name, len(hit), sum(r["y"] for r in hit), f"{sum(r['y'] for r in hit) / len(hit):.0%}",
                    f"{sum(r['y'] for r in alone)}/{len(alone)}"])
    bm.table(["Signal", "Fires", "NBIM against", "Share", "While trusted: against/fires"], out)
    print(f"   A signal is trusted once NBIM has followed it at {TRUST_AFTER} meetings in a row, and loses the trust at the first miss.")

    print("\n6. As a predictor of 'against the board', all years")
    any_signal = [r for r in rows if r["signals"]]
    alone = [r for r in rows if r["acts_alone"]]
    last = [r for r in rows if r["prev_same_item"] == 1]
    out = [line("Always with board", [], len(against)),
           line("Same as last time", last, len(against)),
           line("Before: rules on SEC insider filings, with the old monitor",
                [r for r in rows if r["sec_rules"] and any(v == "active" for v in r["sec_state"].values())], len(against)),
           line("Any signal fires (no trust rule)", any_signal, len(against)),
           line("Trusted signals only: the tool acts alone", alone, len(against)),
           line("Trusted signals, or same as last time", [r for r in rows if r["acts_alone"] or r["prev_same_item"] == 1], len(against))]
    bm.table(["Method", "Flags", "Hits", "False alarms", "Precision", "Recall"], out)
    held = [r for r in any_signal if not r["acts_alone"]]
    print(f"   Signals that fired without trust send {len(held)} more nominees to a person, {sum(r['y'] for r in held)} of them "
          f"against-votes. So {sum(r['y'] for r in any_signal)} of the {len(against)} against-votes are either suggested or put in "
          f"front of a person with the fact and its quote.")

    print("\n7. By period")
    out = []
    for lab, keep in (("2019-2024", lambda y: y <= "2024"), ("2025", lambda y: y == "2025"), ("2026", lambda y: y == "2026"),
                      ("all years", lambda y: True)):
        f = [r for r in any_signal if keep(r["meeting_date"][:4])]
        act = [r for r in f if r["acts_alone"]]
        rest = [r for r in f if not r["acts_alone"]]
        base = [r for r in last if keep(r["meeting_date"][:4])]
        out.append([lab, sum(r["y"] for r in rows if keep(r["meeting_date"][:4])), f"{sum(r['y'] for r in base)}/{len(base)}",
                    f"{sum(r['y'] for r in act)}/{len(act)}", f"{sum(r['y'] for r in rest)}/{len(rest)}"])
    bm.table(["Years", "Against-votes", "Same as last time: hits/flags", "Tool acts alone: hits/flags",
              "Sent to a person with the fact: against/total"], out)

    print("\n8. The against-votes no signal points at, by NBIM's stated reason")
    missed = [r for r in against if not r["signals"]]
    print(f"   {len(missed)} of {len(against)}: " + ", ".join(f"{k or 'none given'} {v}" for k, v in
                                                            C(r["rationale_section"] for r in missed).most_common()))
    print("   GVG 3.2 is 'board decisions and conduct': a reaction to something the company did, which a proxy does not state.")

    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["meeting_id", "item_no", "meeting_date", "company", "nominee", "proxy_url", "independent", "executive",
                    "ceo", "board_chair", "audit_committee", "pay_committee", "nomination_committee", "other_public_boards",
                    "signals_acted_on_alone", "signals_sent_to_a_person", "other_notes_for_the_reviewer", "quotes",
                    "actual_against_board", "nbim_stated_reason"])
        for r in rows:
            n = r["n"] or {}
            quotes = " | ".join(f"{k}: \"{n[k]['quote']}\"" for k in fb.QUOTED if n.get(k, {}).get("verified") and n[k]["quote"]) if n.get("found") else ""
            shown = lambda v: "; ".join(v) if isinstance(v, list) else v
            tell = lambda g: f"{g['text']} [NBIM followed this at {g['record']} earlier meetings]"
            w.writerow([r["meeting_id"], r["item_no"], r["meeting_date"], r["company"], dr.nominee_name(r["proposal_text"]),
                        (r["proxy"] or {}).get("url", "")] +
                       [shown(val(n, k)) if n.get("found") else "" for k in ("independent", "executive", "ceo", "board_chair", "audit_committee",
                                                                            "pay_committee", "nomination_committee", "other_public_boards")] +
                       [" | ".join(tell(g) for g in r["acts_alone"]),
                        " | ".join(tell(g) + ("" if g["quoted"] else " [quote not found]") for g in r["signals"] if g not in r["acts_alone"]),
                        " | ".join(t for _, t, lab in r["notes"] if lab not in OWN_READING), quotes, r["y"], r["rationale_section"]])
    print(f"\nWrote {len(rows)} nominees to {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
