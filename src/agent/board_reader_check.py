"""How reliable is the proxy reader? A second, stronger model read a sample again.

Run from the repo root (no internet, no API key; both readers' answers are cached):
    python3 src/agent/board_reader_check.py

fetch_board_facts.py reads every proxy with Claude Haiku 5.5. For a random
sample of meetings (seed 7) a second model, Claude Sonnet 5.5, was given
exactly the same passages, the same names and the same questions
(fetch_board_facts.py --check 16). Only the model differs.

This script compares the two sets of answers, fact by fact, and then asks the
question that matters for the tool: would NBIM's rules have fired on the same
nominees with the second reader's facts?

Two things this is not. It is not accuracy: both readers can be wrong in the
same way, and nobody checked the answers by hand. And it is a small sample:
13 of the 16 meetings drawn were read (the last three were refused by the
account's credit check), 3 of 36 companies appear twice.
"""

import collections
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "src", "agent"))
from benchmark import model as bm  # noqa: E402
import board_rules as br  # noqa: E402
import fetch_board_facts as fb  # noqa: E402

UNKNOWN = ("unknown", None)


def same(a, b, kind):
    if kind == "names":
        return len(a) == len(b)
    if kind == "number":
        return abs(a - b) < 1.01 if max(a, b) > 20 else a == b      # percentages may differ by rounding
    return a == b


def compare(pairs, questions):
    """pairs: (first reader's facts, second reader's facts). One table row per question."""
    out = []
    for key, kind, _ in questions:
        both = [(a[key]["answer"], b[key]["answer"]) for a, b in pairs
                if a[key]["answer"] not in UNKNOWN and b[key]["answer"] not in UNKNOWN]
        only_first = sum(1 for a, b in pairs if a[key]["answer"] not in UNKNOWN and b[key]["answer"] in UNKNOWN)
        only_second = sum(1 for a, b in pairs if a[key]["answer"] in UNKNOWN and b[key]["answer"] not in UNKNOWN)
        agree = sum(1 for x, y in both if same(x, y, kind))
        out.append([key, len(both), agree, f"{agree / len(both):.0%}" if both else "-", only_first, only_second])
    return out


def main():
    first, second = fb.load_cache(), fb.load_cache(fb.CHECK_CACHE)
    keys = sorted(k for k in second if k in first)
    if not keys:
        raise SystemExit("No second-reader answers. Run src/agent/fetch_board_facts.py --check 16 first.")
    nominees, boards = [], []
    for k in keys:
        boards.append((first[k]["answers"]["board"], second[k]["answers"]["board"]))
        for a, b in zip(first[k]["answers"]["nominees"], second[k]["answers"]["nominees"]):
            br.mark_founder(a, first[k]["company"])
            br.mark_founder(b, first[k]["company"])
            if a["found"] and b["found"]:
                nominees.append((a, b, first[k]["answers"]["board"], second[k]["answers"]["board"], first[k]))
    print(f"Meetings read by both models: {len(keys)} ({len({k[0] for k in keys})} companies), {len(nominees)} nominees.")
    print(f"First reader {fb.MODEL}, second reader {fb.CHECK_MODEL}. Same passages, names and questions.\n")

    print("1. Facts about each nominee")
    table = compare([(a, b) for a, b, _, _, _ in nominees], fb.NOMINEE_QUESTIONS)
    bm.table(["Fact", "Both answered", "Same answer", "Share", "Only the first answered", "Only the second answered"], table)
    answered = sum(r[1] for r in table)
    agreed = sum(r[2] for r in table)
    print(f"   Over all facts: the same answer on {agreed} of {answered} ({agreed / answered:.1%}) where both answered.")
    print("   'other_public_boards' counts as the same when both list the same number of companies.")

    print("\n2. Facts about the board")
    bm.table(["Fact", "Both answered", "Same answer", "Share", "Only the first answered", "Only the second answered"],
             compare(boards, fb.BOARD_QUESTIONS))

    print("\n3. Would NBIM's rules fire on the same nominees?")
    fired = collections.Counter()
    differ = []
    for a, b, board_a, board_b, rec in nominees:
        ra = sorted(br.rule_id(t) for _, t, _ in br.decide(a, board_a))
        rb = sorted(br.rule_id(t) for _, t, _ in br.decide(b, board_b))
        fired[(bool(ra), bool(rb))] += 1
        if ra != rb:
            differ.append((rec["company"], rec["meeting_date"], a["ballot_name"], ra, rb))
    bm.table(["", "Second reader: a rule fires", "Second reader: none"],
             [["First reader: a rule fires", fired[(True, True)], fired[(True, False)]],
              ["First reader: none", fired[(False, True)], fired[(False, False)]]])
    same_outcome = len(nominees) - len(differ)
    print(f"   The same rules fire, or none, for {same_outcome} of {len(nominees)} nominees ({same_outcome / len(nominees):.1%}).")
    for company, date, name, ra, rb in differ:
        print(f"   differs: {company} {date}, {name}: first reader {ra or 'none'}, second reader {rb or 'none'}")

    print("\n4. Where the two disagree on the facts the rules rest on, after the two corrections made in code")
    print("   (an 'executive' the company calls independent is not one; 'founder' must be of this company)")
    shown = 0
    for a, b, _, _, rec in nominees:
        for key in ("independent", "executive", "ceo", "board_chair", "founder"):
            x, y = a[key]["answer"], b[key]["answer"]
            if key == "executive":      # what the rules use: an "executive" the company calls independent is not one
                x, y = br.is_executive(a), br.is_executive(b)
            if key == "founder":        # what the rules use: founder of this company
                x, y = ("yes" if a["founder_here"] else "no"), ("yes" if b["founder_here"] else "no")
            if x not in UNKNOWN and y not in UNKNOWN and x != y:
                shown += 1
                print(f"   {rec['company']} {rec['meeting_date']}, {a['ballot_name']}, {key}: first '{x}' (\"{a[key]['quote'][:90]}\") "
                      f"| second '{y}' (\"{b[key]['quote'][:90]}\")")
    if not shown:
        print("   None.")
    print("\n   Reading this: agreement between two models is not the same as being right, and the sample is small.")
    print("   It does show which facts are stable enough to act on (roles, independence, committees) and which")
    print("   are not (counts that depend on what one calls a listed company).")


if __name__ == "__main__":
    main()
