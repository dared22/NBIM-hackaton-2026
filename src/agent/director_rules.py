"""Director elections at US companies: NBIM's written rules applied to dated facts.

Run from the repo root (no internet, no API key, no AI model):
    python3 src/agent/director_rules.py

Idea
    NBIM's voting guidelines contain clear-cut rules about directors, for example
        1.3.1  "We will not support the election of a chairperson who is also
                the CEO of the company."
        2.1.1  no support for a director "who sits on more than five boards"
    A rule plus a fact gives a vote, and the rule to cite, without any training.
    Because nothing is fitted, every year in the file is a fair test.

Facts
    data/evidence/director_roles.csv, built by fetch_director_roles.py from the
    SEC's Insider Transactions Data Sets. For each person it says at which
    companies they reported as director or officer, when, and with what title.

    For a nominee at a meeting, only reports from months before the meeting
    month are used:
        chair and CEO   the person's latest officer title at this company in
                        the 36 months before names both a chair and a CEO role
        executive       the person reported as an officer of this company in
                        the 24 months before
        boards          number of companies where the person reported as a
                        director in the 24 months before, this one included

Known gaps, stated up front
    - Only boards of US-listed companies are counted, and only where the
      person filed a report in the window. The count is a lower bound.
    - A title is what the company wrote on the form. A CEO who also chairs the
      board but is titled just "CEO" is not seen as combined.
    - Nominees are matched to people by name within the company. New nominees
      who have not yet filed any report cannot be matched.
    - The 2025 guidelines are applied to all years.

Drift monitor
    NBIM can stop applying a rule. So each rule is watched: if NBIM supported
    the board the last two times the rule fired, the rule is suspended, and
    its later cases go to a person instead of being suggested as "against".
    The monitor only uses votes from earlier meeting dates, which NBIM itself
    would know.

Answer key: data/dirty/real_votes.csv (36 US companies). The rule decisions
use no votes. The drift monitor and the scoring do.
"""

import collections
import csv
import datetime
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))
from benchmark import model as bm  # noqa: E402

VOTES = os.path.join(ROOT, "data", "dirty", "real_votes.csv")
ROLES = os.path.join(ROOT, "data", "evidence", "director_roles.csv")
OUT = os.path.join(ROOT, "data", "outputs", "director_rules.csv")
SUFFIX = {"JR", "SR", "II", "III", "IV", "V", "PHD", "MD", "CPA", "ESQ"}
CEO = re.compile(r"\bceo\b|chief exec|c\.e\.o", re.I)
CHAIR = re.compile(r"(?<!vice )(?<!vice-)chair", re.I)
MAX_BOARDS = 5


def name_tokens(name):
    name = re.sub(r"\"[^\"]*\"|\([^)]*\)", " ", name.upper())      # drop nicknames in quotes or brackets
    return [t for t in re.sub(r"[^A-Z ]", " ", name).split() if t not in SUFFIX]


def nominee_name(proposal_text):
    m = re.match(r"elect director (.+)", proposal_text.strip(), re.I)
    return m.group(1) if m else None


def same_person(nominee, filed):
    """Ballot name 'Michael S. Dell' against SEC name 'DELL MICHAEL S'. Returns a score, 0 = no match."""
    a, b = name_tokens(nominee), name_tokens(filed)
    if len(a) < 2 or len(b) < 2:
        return 0
    last, first = a[-1], a[0]
    if last not in b:
        # two-word surnames: 'de la Cruz' is filed as 'DE LA CRUZ JOHN'
        if not (len(a) >= 3 and " ".join(a[-2:]) in " ".join(b)):
            return 0
    rest = [t for t in b if t != last]
    if first in rest:
        return 3
    if any(t.startswith(first) or first.startswith(t) for t in rest if len(t) >= 3 and len(first) >= 3):
        return 2  # Tom / Thomas, Rob / Robert
    if any(len(t) == 1 and t == first[0] for t in rest) or (len(first) == 1 and any(t.startswith(first) for t in rest)):
        return 1  # only an initial on one side
    return 0


def months_before(date, months):
    d = datetime.date.fromisoformat(date)
    total = d.year * 12 + d.month - 1 - months
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def load_roles():
    people_at = collections.defaultdict(dict)      # company_id -> person_cik -> name
    reports = collections.defaultdict(list)        # person_cik -> [(month, issuer_cik, relationship, title, company_id)]
    with open(ROLES, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r["company_id"]:
                people_at[r["company_id"]][r["person_cik"]] = r["person_name"]
            reports[r["person_cik"]].append((r["month"], r["issuer_cik"], r["relationship"], r["title"], r["company_id"]))
    return people_at, reports


def facts_for(row, people_at, reports):
    """Facts about one nominee, from reports filed in months before the meeting month."""
    name = nominee_name(row["proposal_text"])
    if not name:
        return None
    best = max(((same_person(name, filed), cik) for cik, filed in people_at.get(row["company_id"], {}).items()),
               default=(0, None))
    if best[0] == 0:
        return {"matched": False, "nominee": name}
    person = best[1]
    month = row["meeting_date"][:7]
    seen = [r for r in reports[person] if r[0] < month]
    here36 = [r for r in seen if r[4] == row["company_id"] and r[0] >= months_before(row["meeting_date"], 36)]
    recent = [r for r in seen if r[0] >= months_before(row["meeting_date"], 24)]
    titles = [r for r in sorted(here36) if r[3]]
    title = titles[-1][3] if titles else ""
    boards = {r[1] for r in recent if "Director" in r[2]}
    return {
        "matched": True, "nominee": name, "person_cik": person, "sec_name": people_at[row["company_id"]][person],
        "title": title, "title_month": titles[-1][0] if titles else "",
        "chair_ceo": bool(title and CEO.search(title) and CHAIR.search(title)),
        "executive": any("Officer" in r[2] for r in recent if r[4] == row["company_id"]),
        "boards": len(boards | ({here36[-1][1]} if here36 else set())),
        "has_reports": bool(seen),
    }


def decide(f):
    """NBIM rules that the facts trigger. Returns a list of (rule id, reason)."""
    out = []
    if not f or not f["matched"]:
        return out
    if f["chair_ceo"]:
        out.append(("GVG 1.3", f"rule 1.3.1: titled \"{f['title']}\" (report of {f['title_month']}), chair and CEO combined"))
    if f["boards"] > MAX_BOARDS:
        out.append(("GVG 2.1", f"rule 2.1.1: reported as director at {f['boards']} US-listed companies in the two years before"))
    return out


def run_monitor(rows, misses_to_suspend=2):
    """Mark each fired rule as 'active' or 'suspended', going through meetings in date order.

    A rule is suspended once NBIM has supported the board on its last
    `misses_to_suspend` cases. Cases on the same date do not see each other.
    """
    streak = collections.Counter()       # rule -> consecutive misses so far
    by_date = collections.defaultdict(list)
    for r in rows:
        by_date[r["meeting_date"]].append(r)
    for date in sorted(by_date):
        for r in by_date[date]:
            r["rule_state"] = {code: ("suspended" if streak[code] >= misses_to_suspend else "active") for code, _ in r["rules"]}
        for r in by_date[date]:
            for code, _ in r["rules"]:
                streak[code] = 0 if r["y"] else streak[code] + 1


def rate(rows):
    return f"{sum(r['y'] for r in rows) / len(rows):.1%}" if rows else "-"


def load_scored():
    """Every US director nominee with facts, triggered rules and the monitor's state."""
    rows = [r for r in bm.read_votes(VOTES) if r["country"] == "United States" and r["proposal_type"] == "DIRECTOR_ELECTION"
            and nominee_name(r["proposal_text"])]
    bm.add_history_features(rows)     # only for the "same as last time" baseline
    people_at, reports = load_roles()
    for r in rows:
        r["f"] = facts_for(r, people_at, reports)
        r["rules"] = decide(r["f"])
    run_monitor(rows)
    return rows


def main():
    rows = load_scored()
    C = collections.Counter
    matched = [r for r in rows if r["f"]["matched"]]
    against = [r for r in rows if r["y"]]

    print(f"US director elections in NBIM's file: {len(rows)} nominees at {len({r['company_id'] for r in rows})} companies, "
          f"{len({r['meeting_id'] for r in rows})} meetings, {min(r['meeting_date'] for r in rows)[:4]}-{max(r['meeting_date'] for r in rows)[:4]}")
    print(f"NBIM voted against the board on {len(against)} ({rate(rows)}).")
    print(f"Nominees matched to a person in the SEC data: {len(matched)} ({len(matched) / len(rows):.0%}); "
          f"of the against-votes: {sum(1 for r in against if r['f']['matched'])} of {len(against)}.\n")

    print("1. What the facts show (matched nominees)")
    bm.table(["Fact about the nominee", "Nominees", "NBIM against", "Against rate"],
             [[lab, len(b), sum(r["y"] for r in b), rate(b)] for lab, b in (
                 ("chair and CEO combined", [r for r in matched if r["f"]["chair_ceo"]]),
                 ("executive, not chair and CEO", [r for r in matched if r["f"]["executive"] and not r["f"]["chair_ceo"]]),
                 ("not an executive", [r for r in matched if not r["f"]["executive"]]),
                 ("on 1 US board", [r for r in matched if r["f"]["boards"] <= 1]),
                 ("on 2 US boards", [r for r in matched if r["f"]["boards"] == 2]),
                 ("on 3 US boards", [r for r in matched if r["f"]["boards"] == 3]),
                 ("on 4-5 US boards", [r for r in matched if 4 <= r["f"]["boards"] <= 5]),
                 ("on more than 5 US boards", [r for r in matched if r["f"]["boards"] > 5]),
                 ("not matched to a person", [r for r in rows if not r["f"]["matched"]]))])

    print("\n2. NBIM's rules as a predictor (no training, all years)")
    fired = [r for r in rows if r["rules"]]
    base = [r for r in rows if r["prev_same_item"] == 1]
    either = [r for r in rows if r["rules"] or r["prev_same_item"] == 1]
    out = []
    for lab, flagged in (("Always with board", []), ("Same as last time", base),
                         ("Rule 1.3.1, chair who is also CEO", [r for r in rows if any(c == "GVG 1.3" for c, _ in r["rules"])]),
                         ("Rule 2.1.1, more than five boards", [r for r in rows if any(c == "GVG 2.1" for c, _ in r["rules"])]),
                         ("Either rule", fired), ("Same as last time, or either rule", either)):
        hits = sum(r["y"] for r in flagged)
        out.append([lab, len(flagged), hits, len(flagged) - hits, f"{hits / len(flagged):.0%}" if flagged else "-",
                    f"{hits / len(against):.0%}"])
    bm.table(["Method", "Flags", "Hits", "False alarms", "Precision", "Recall"], out)
    new = [r for r in against if r["prev_same_item"] != 1]
    print(f"\n   Against-votes on people NBIM had not opposed before: {len(new)}. The rules find "
          f"{sum(1 for r in new if r['rules'])}; 'same as last time' finds 0 by construction.")

    print("\n3. Does the tool cite the rule NBIM itself gave?")
    for code, name in (("GVG 1.3", "chair and CEO"), ("GVG 2.1", "time commitment")):
        nb = [r for r in against if r["rationale_section"] == code]
        ours = [r for r in rows if any(c == code for c, _ in r["rules"])]
        print(f"   {code} ({name}): NBIM cited it for {len(nb)} against-votes; the rule fired on {len(ours)} nominees "
              f"and matched {sum(1 for r in nb if any(c == code for c, _ in r['rules']))} of NBIM's {len(nb)}. "
              f"When the rule fired and NBIM voted against, NBIM's stated reason was: "
              f"{dict(C(r['rationale_section'] or 'none given' for r in ours if r['y']))}")

    print("\n4. Policy and practice: nominees titled chair and CEO, by year")
    cc = [r for r in matched if r["f"]["chair_ceo"]]
    bm.table(["Year", "Chair-and-CEO nominees", "NBIM against", "Against rate"],
             [[y, len(b), sum(r["y"] for r in b), rate(b)] for y, b in
              ((y, [r for r in cc if r["meeting_date"][:4] == y]) for y in sorted({r["meeting_date"][:4] for r in cc}))])
    by_co = collections.defaultdict(list)
    for r in cc:
        by_co[r["company"]].append(r)
    print("   By company (against / elections): " + "; ".join(
        f"{k} {sum(r['y'] for r in v)}/{len(v)}" for k, v in sorted(by_co.items(), key=lambda kv: -len(kv[1]))))

    print("\n5. With the drift monitor (a rule is suspended after NBIM supported the board on its last two cases)")
    auto = [r for r in rows if any(v == "active" for v in r["rule_state"].values())]
    held = [r for r in rows if r["rules"] and r not in auto]
    out = []
    for lab, years in (("2019-2025", lambda y: y <= "2025"), ("2026", lambda y: y == "2026"), ("all years", lambda y: True)):
        a = [r for r in auto if years(r["meeting_date"][:4])]
        h = [r for r in held if years(r["meeting_date"][:4])]
        nomon = [r for r in rows if r["rules"] and years(r["meeting_date"][:4])]
        out.append([lab, f"{sum(r['y'] for r in nomon)}/{len(nomon)}", f"{sum(r['y'] for r in a)}/{len(a)}",
                    f"{sum(r['y'] for r in h)}/{len(h)}"])
    bm.table(["Years", "Rules alone: hits/flags", "Monitor: automatic hits/flags", "Monitor: sent to a person, against/total"], out)
    first = collections.defaultdict(str)
    for r in sorted(held, key=lambda r: r["meeting_date"]):
        for code, state in r["rule_state"].items():
            if state == "suspended" and not first[code]:
                first[code] = r["meeting_date"]
    print("   Rules suspended from: " + (", ".join(f"{k} on {v}" for k, v in sorted(first.items())) or "none"))

    print("\n6. Against-votes the rules do not explain, by NBIM's stated reason")
    print("   ", dict(C(r["rationale_section"] or "none given" for r in against if not r["rules"]).most_common()))

    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["meeting_id", "item_no", "meeting_date", "company", "nominee", "matched_person", "sec_person_page",
                    "title", "executive", "us_boards", "rules_triggered", "reasons", "rule_state", "same_as_last_time",
                    "actual_against", "nbim_stated_reason"])
        for r in sorted(rows, key=lambda r: (r["meeting_date"], r["company"], int(r["item_no"]))):
            fct = r["f"]
            w.writerow([r["meeting_id"], r["item_no"], r["meeting_date"], r["company"], fct["nominee"],
                        fct.get("sec_name", ""),
                        f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={fct['person_cik']}&type=4" if fct["matched"] else "",
                        fct.get("title", ""), int(fct.get("executive", False)), fct.get("boards", ""),
                        ", ".join(c for c, _ in r["rules"]), " | ".join(t for _, t in r["rules"]),
                        ", ".join(f"{k} {v}" for k, v in r["rule_state"].items()),
                        int(r["prev_same_item"] == 1), r["y"], r["rationale_section"]])
    print(f"\nWrote {len(rows)} nominees to {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
