"""Director elections in Japan and Korea: a company fact that sends the nominee to a person.

Run from the repo root (no internet, no API key):
    python3 src/agent/country_rules.py

The facts come from Marie's work on branch marie: Japan's EDINET annual securities
reports (each director's title, and how many of the proposed board are independent)
and Korea's OpenDART. They are exported per proposal to
data/evidence/jev_pipeline/company_facts.csv by src/agent/export_company_facts.py.
Every fact is from a document filed before the meeting. The file holds no NBIM vote.

What the votes show (years up to 2025)
    Japan   NBIM's against-votes fall on the top executive. Of 197 nominees who are
            representative directors, it opposed 27. Of 683 nominees matched to any
            other role (outside director, other executive, inside director) it opposed
            none. Among representative directors it is the chairman or president, and
            more often where less than half of the board is independent. NBIM names
            board independence (section 1.1) for 36 of its 40 against-votes in Japan.
    Korea   The ballot says which nominees are inside directors. NBIM opposed 19 of 66
            of those in 2021-2025.

Neither is close to a rule (about one in four), so the tool never acts on them alone.
They are reasons to put the nominee in front of a person, with the fact.

Honest note: the title pattern (chairman or president, not vice) and the "less than half"
level were chosen after looking at the votes up to 2025. 2026 was not used.
"""

import collections
import csv
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))
from benchmark import model as bm  # noqa: E402

VOTES = os.path.join(ROOT, "data", "dirty", "real_votes.csv")
FACTS = os.path.join(ROOT, "data", "evidence", "jev_pipeline", "company_facts.csv")
TOP_TITLE = re.compile(r"会長|社長")          # chairman or president
NOT_TOP = re.compile(r"副社長|副会長")        # vice president, vice chairman
INDEPENDENT_ENOUGH = 0.5

_FACTS = {}


def load_facts():
    if not _FACTS:
        with open(FACTS, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                _FACTS[(r["meeting_id"], r["item_no"])] = r
    return _FACTS


def number(fact, key):
    return float(fact[key]) if fact and fact.get(key, "") != "" else None


def japan_role(fact):
    """The nominee's role in the EDINET report, or None when the report or the nominee was not found."""
    if not fact or fact["jp_found"] != "1" or number(fact, "jp_nominee_found") != 1:
        return None
    if number(fact, "jp_nominee_representative") == 1:
        title = fact["jp_nominee_title"]
        return "top executive" if TOP_TITLE.search(title) and not NOT_TOP.search(title) else "other representative director"
    if number(fact, "jp_nominee_outside") == 1:
        return "outside director"
    return "other executive" if number(fact, "jp_nominee_executive") == 1 else "inside director"


def signal_for(row):
    """(guideline section, the fact in words) when a fact applies that should bring in a person, else None."""
    if row["proposal_type"] != "DIRECTOR_ELECTION":
        return None
    fact = load_facts().get((row["meeting_id"], row["item_no"]))
    if row["country"] == "Japan":
        share = number(fact, "jp_independent_share")
        if japan_role(fact) == "top executive" and share is not None and share < INDEPENDENT_ENOUGH:
            return ("GVG 1.1", f"the nominee is the company's top executive ({fact['jp_nominee_title'][:24]}, a representative "
                    f"director) and {share:.0%} of the proposed board is independent, from the EDINET report filed before "
                    f"the meeting; in Japan NBIM's against-votes fall on the top executive at boards like this")
    if row["country"] == "South Korea" and "inside director" in row["proposal_text"].lower():
        return ("", "the ballot names this nominee an inside director; NBIM opposes about one in four inside directors in Korea")
    return None


def main():
    rows = bm.read_votes(VOTES)
    facts = load_facts()
    year = lambda r: r["meeting_date"][:4]
    jp = [r for r in rows if r["country"] == "Japan" and r["proposal_type"] == "DIRECTOR_ELECTION"]
    print(f"Japan: {len(jp)} director nominees in NBIM's file, {sum(r['y'] for r in jp)} against the board. "
          f"EDINET report found for {sum(1 for r in jp if facts.get((r['meeting_id'], r['item_no']), {}).get('jp_found') == '1')}.")
    print("\n1. By the nominee's role in the report")
    out = []
    for period, keep in (("to 2025", lambda y: y <= "2025"), ("2026", lambda y: y == "2026")):
        cells = collections.defaultdict(lambda: [0, 0])
        for r in jp:
            if keep(year(r)):
                role = japan_role(facts.get((r["meeting_id"], r["item_no"]))) or "report or nominee not found"
                cells[role][0] += 1
                cells[role][1] += r["y"]
        out += [[period, role, n, k, f"{k / n:.1%}"] for role, (n, k) in sorted(cells.items())]
    bm.table(["Years", "Role", "Nominees", "NBIM against", "Share"], out)

    print("\n2. Top executives, by how much of the proposed board is independent")
    out = []
    for period, keep in (("to 2025", lambda y: y <= "2025"), ("2026", lambda y: y == "2026")):
        cells = collections.defaultdict(lambda: [0, 0])
        for r in jp:
            fact = facts.get((r["meeting_id"], r["item_no"]))
            share = number(fact, "jp_independent_share")
            if keep(year(r)) and japan_role(fact) == "top executive" and share is not None:
                label = "under a third" if share < 1 / 3 else "a third to under half" if share < 0.5 else "half or more"
                cells[label][0] += 1
                cells[label][1] += r["y"]
        out += [[period, label, n, k, f"{k / n:.0%}"] for label, (n, k) in sorted(cells.items())]
    bm.table(["Years", "Independent share of the board", "Top executives", "NBIM against", "Share"], out)

    print("\n3. The two facts as reasons to bring in a person, by year")
    out = []
    for y in sorted({year(r) for r in rows}):
        fired = [r for r in rows if year(r) == y and signal_for(r)]
        if fired:
            jpn = [r for r in fired if r["country"] == "Japan"]
            kor = [r for r in fired if r["country"] == "South Korea"]
            out.append([y, len(jpn), sum(r["y"] for r in jpn), len(kor), sum(r["y"] for r in kor)])
    bm.table(["Year", "Japan: top executive, board under half independent", "NBIM against",
              "Korea: inside director", "NBIM against"], out)
    print("   What these add to the pipeline is in src/agent/combined_model.py and the model card: on 2022-2025 they")
    print("   put 11 more against-votes in front of a person for 78 more nominees read.")


if __name__ == "__main__":
    main()
