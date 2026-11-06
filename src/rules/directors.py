"""rules.directors: NBIM voting decision support."""

import collections
import csv
import datetime
import re

from src import data as paths
from src.models import history as bm

VOTES = paths.VOTES
ROLES = paths.DIRECTOR_ROLES
SUFFIX = {"JR", "SR", "II", "III", "IV", "V", "PHD", "MD", "CPA", "ESQ"}
CEO = re.compile(r"\bceo\b|chief exec|c\.e\.o", re.I)
CHAIR = re.compile(r"(?<!vice )(?<!vice-)chair", re.I)
MAX_BOARDS = 5


def name_tokens(name):
    name = re.sub(
        r"\"[^\"]*\"|\([^)]*\)", " ", name.upper()
    )  # drop nicknames in quotes or brackets
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
    if any(
        t.startswith(first) or first.startswith(t) for t in rest if len(t) >= 3 and len(first) >= 3
    ):
        return 2  # Tom / Thomas, Rob / Robert
    if any(len(t) == 1 and t == first[0] for t in rest) or (
        len(first) == 1 and any(t.startswith(first) for t in rest)
    ):
        return 1  # only an initial on one side
    return 0


def months_before(date, months):
    d = datetime.date.fromisoformat(date)
    total = d.year * 12 + d.month - 1 - months
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def load_roles():
    people_at = collections.defaultdict(dict)  # company_id -> person_cik -> name
    reports = collections.defaultdict(
        list
    )  # person_cik -> [(month, issuer_cik, relationship, title, company_id)]
    with open(ROLES, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r["company_id"]:
                people_at[r["company_id"]][r["person_cik"]] = r["person_name"]
            reports[r["person_cik"]].append(
                (r["month"], r["issuer_cik"], r["relationship"], r["title"], r["company_id"])
            )
    return people_at, reports


def facts_for(row, people_at, reports):
    """Facts about one nominee, from reports filed in months before the meeting month."""
    name = nominee_name(row["proposal_text"])
    if not name:
        return None
    best = max(
        (
            (same_person(name, filed), cik)
            for cik, filed in people_at.get(row["company_id"], {}).items()
        ),
        default=(0, None),
    )
    if best[0] == 0:
        return {"matched": False, "nominee": name}
    person = best[1]
    month = row["meeting_date"][:7]
    seen = [r for r in reports[person] if r[0] < month]
    here36 = [
        r
        for r in seen
        if r[4] == row["company_id"] and r[0] >= months_before(row["meeting_date"], 36)
    ]
    recent = [r for r in seen if r[0] >= months_before(row["meeting_date"], 24)]
    titles = [r for r in sorted(here36) if r[3]]
    title = titles[-1][3] if titles else ""
    boards = {r[1] for r in recent if "Director" in r[2]}
    return {
        "matched": True,
        "nominee": name,
        "person_cik": person,
        "sec_name": people_at[row["company_id"]][person],
        "title": title,
        "title_month": titles[-1][0] if titles else "",
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
        out.append(
            (
                "GVG 1.3",
                f'rule 1.3.1: titled "{f["title"]}" (report of {f["title_month"]}), chair and CEO combined',
            )
        )
    if f["boards"] > MAX_BOARDS:
        out.append(
            (
                "GVG 2.1",
                f"rule 2.1.1: reported as director at {f['boards']} US-listed companies in the two years before",
            )
        )
    return out


def run_monitor(rows, misses_to_suspend=2):
    """Mark each fired rule as 'active' or 'suspended', going through meetings in date order.

    A rule is suspended once NBIM has supported the board on its last
    `misses_to_suspend` cases. Cases on the same date do not see each other.
    """
    streak = collections.Counter()  # rule -> consecutive misses so far
    by_date = collections.defaultdict(list)
    for r in rows:
        by_date[r["meeting_date"]].append(r)
    for date in sorted(by_date):
        for r in by_date[date]:
            r["rule_state"] = {
                code: ("suspended" if streak[code] >= misses_to_suspend else "active")
                for code, _ in r["rules"]
            }
        for r in by_date[date]:
            for code, _ in r["rules"]:
                streak[code] = 0 if r["y"] else streak[code] + 1


def load_scored():
    """Every US director nominee with facts, triggered rules and the monitor's state."""
    rows = [
        r
        for r in bm.read_votes(VOTES)
        if r["country"] == "United States"
        and r["proposal_type"] == "DIRECTOR_ELECTION"
        and nominee_name(r["proposal_text"])
    ]
    bm.add_history_features(rows)  # only for the "same as last time" baseline
    people_at, reports = load_roles()
    for r in rows:
        r["f"] = facts_for(r, people_at, reports)
        r["rules"] = decide(r["f"])
    run_monitor(rows)
    return rows
