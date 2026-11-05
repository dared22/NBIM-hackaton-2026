"""Do NBIM's position papers add anything to the tool? Four tests.

Run from the repo root (no internet; the decision-model answers are cached):
    python3 src/agent/position_papers_test.py

The case names two policy sources: the Global Voting Guidelines and the
position papers. The guidelines were already in the tool. The papers are in
data/policy/position_papers.json (fetch_position_papers.py).

    1. What do the papers say that the guidelines do not? Sentences with a
       number or a threshold in NBIM's stated positions.
    2. One new threshold can be checked against votes: share issues without
       pre-emptive rights "should not exceed 10 percent".
    3. NBIM names a position paper next to many of its against-votes. When
       one of our rules fires, does the paper for that rule match NBIM's?
    4. Does the decision model (rule check on the proposal wording) get
       better when it is also given the paper for each guideline section?
"""

import collections
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "src", "agent"))
from benchmark import model as bm  # noqa: E402
import director_rules as dr  # noqa: E402
import proposal_rules as pr  # noqa: E402
import rule_check as rc  # noqa: E402

NUMBER = re.compile(r"\b(\d+|one|two|three|five|ten|third|majority|percent)\b", re.I)
YEAR = 2026


def paper_title(section, papers, rule=""):
    p = rc.paper_for(papers, section, rule)
    return "Position paper: " + p["title"] if p else ""


def main():
    papers = rc.load_papers()
    rows = bm.read_votes(rc.VOTES)
    C = collections.Counter

    print(f"{len(papers)} position papers loaded: " + ", ".join(p["title"] for p in papers.values()) + "\n")

    print("1. Statements with a number or threshold in NBIM's positions")
    for p in papers.values():
        for sentence in re.split(r"(?<=[.])\s+", " ".join(p["position"].split())):
            if NUMBER.search(sentence):
                print(f"   [{p['title']}] {sentence}")
    print("\n   Most repeat the guidelines (five boards, half independent, a third at controlled companies,")
    print("   three years and three percent for proxy access). New compared with the guidelines:")
    print("   - share issues without pre-emptive rights should not exceed 10 percent; authorities at most 15 months")
    print("   - a chair of a leading company should not chair another company")
    print("   - boards with under 30 percent of either gender should set targets")
    print("   - at least two independent members should have worked in the industry")
    print("   - pay: shares locked in for five to ten years; no number for how much pay is too much")

    print("\n2. The 10 percent threshold for share issues, against NBIM's votes")
    issues = [r for r in rows if r["proposal_type"] == "SHARE_ISSUANCE"]
    pct = lambda t: [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s?(?:percent|%)", t.lower())]
    stated = [r for r in issues if pct(r["proposal_text"])]
    print(f"   {len(issues)} share issue proposals, {sum(r['y'] for r in issues)} against the board. "
          f"Only {len(stated)} state a percentage in the title.")
    cells = collections.defaultdict(lambda: [0, 0])
    for r in stated:
        t = r["proposal_text"].lower()
        without = bool(re.search(r"without pre-?emptive|exclu\w+ (of )?pre-?emptive", t))
        key = ("without pre-emptive rights" if without else "with, or not stated", "over 10%" if max(pct(t)) > 10 else "10% or less")
        cells[key][0] += 1
        cells[key][1] += r["y"]
    bm.table(["Pre-emptive rights", "Size", "Proposals", "NBIM against"], [[a, b, n, k] for (a, b), (n, k) in sorted(cells.items())])
    print("   The threshold cannot be applied to most proposals (no percentage in the title), and where it can,")
    print("   NBIM did not vote against the ones above 10 percent.")

    print("\n3. Does the tool name the same position paper as NBIM?")
    out = []
    for label, scored in (("US director rules", dr.load_scored()), ("wording rules", pr.load_scored())):
        hits = [r for r in scored if r["rules"] and r["y"]]
        ours = lambda r: {paper_title(c, papers, r["rule"][0] if r.get("rule") else "") for c, _ in r["rules"]} - {""}
        named = [r for r in hits if r["position_paper"]]
        same = sum(1 for r in named if any(t in r["position_paper"] for t in ours(r)))
        none_both = sum(1 for r in hits if not r["position_paper"] and not ours(r))
        out.append([label, len(hits), len(named), same, len(hits) - len(named), none_both])
    bm.table(["Rules", "Rule hits", "NBIM named a paper", "Tool names the same paper", "NBIM named none", "Tool also names none"], out)
    print("   NBIM's own pairing of guideline section and paper, all against-votes: " + "; ".join(
        f"{s} -> {p.replace('Position paper: ', '')} ({n})" for (s, p), n in
        C((r["rationale_section"], r["position_paper"].split(";")[0].strip()) for r in rows if r["position_paper"]).most_common(8)))

    print(f"\n4. Decision model on the proposal wording, {YEAR}, with and without the papers")
    sections = rc.load_guidelines()
    cand = rc.candidate_sections(rows, sections)
    _, val, _, _ = bm.run_year(rows, YEAR - 1)
    _, test, _, hist_thr = bm.run_year(rows, YEAR)
    cache = rc.load_cache()
    out = []
    for label, use in (("guidelines only", None), ("guidelines + position papers", papers)):
        rc.fill_cache([rc.build_request(r, cand[r["proposal_type"]], sections, use) for r in val + test], cache)
        rc.attach_scores(val, cand, sections, cache, use)
        rc.attach_scores(test, cand, sections, cache, use)
        thr = bm.best_f1_threshold([r["rule_p"] for r in val], [r["y"] for r in val])
        flags = [r for r in test if r["rule_p"] >= thr]
        new = [r for r in flags if r["p"] < hist_thr]
        cited = [r for r in test if r["y"] and r["rationale_section"].startswith("GVG ")]
        out.append([label, f"{thr:.3f}", len(flags), sum(r["y"] for r in flags), len(flags) - sum(r["y"] for r in flags),
                    f"{sum(r['y'] for r in new)}/{len(new)}",
                    f"{sum(1 for r in cited if r['rationale_section'][4:] == r['rule_section'])}/{len(cited)}"])
    bm.table(["Decision model given", "Cut-off", "Flags", "Hits", "False alarms",
              "New vs history model: hits/flags", "Top section = NBIM's section"], out)
    print(f"   {sum(r['y'] for r in test)} against-votes in {YEAR}. The history model alone finds "
          f"{sum(1 for r in test if r['y'] and r['p'] >= hist_thr)}.")


if __name__ == "__main__":
    main()
