"""Write the results report, and optionally compare it with main's system.

Run from the repository root. Uses saved Jev answers only: no API calls.
    python src/report_results.py                               # data/outputs/jev_results.md
    python src/report_results.py --main-dir <checkout of main> # also the comparison files

Every test year is scored walk-forward, as the pipeline runs live:
  - the combination is fitted on all earlier years with a Jev run, pooled
  - the triage model trains on earlier years only
  - the review share ranks each proposal against the previous 12 months of scores (live)
  - groups NBIM never opposed in 100+ earlier proposals skip review
  - NBIM's rule 1.3.1 (US nominee who is CEO and chair) recommends MOT while its drift monitor allows
Each year is also scored without any company facts (no EDINET, DART, SEC or proxy facts), to show what they add.

The comparison needs a checkout of main where these have been run, for each year:
    python src/benchmark/model.py --data data/dirty/real_votes.csv --test-year <year>
It reads main's per-year scores from src/benchmark/prediksjoner_<year>.csv and main's full
2026 decisions from data/outputs/decisions_2026.csv.
"""

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from sklearn.metrics import average_precision_score

from company_facts import chair_ceo_states, safe_groups
from company_facts import facts as company_facts
from fit_combination import fit
from jev_mvp import DATA, RUNS, build_history_index, combined_score, live_review, load_votes, review_cutoff
from triage_model import score_year

YEARS = (2021, 2022, 2023, 2024, 2025, 2026)  # years with saved Jev runs at history level
TEST_YEARS = YEARS[1:]                          # 2021 has no earlier Jev year to fit on
WITH, WITHOUT = "_v7", "_v5"                     # Jev runs with and without company facts in its input
OUT = DATA / "outputs"
SEEN = {
    2021: "run once, after the design was fixed", 2022: "run once, after the design was fixed",
    2023: "run once, after the design was fixed", 2024: "used to check the design",
    2025: "used to design the system", 2026: "holdout, seen before the design was final",
}


def read(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def metrics(flagged, reviewed, score, actual):
    flagged, reviewed, actual = (np.asarray(x, bool) for x in (flagged, reviewed, actual))
    tp, fp, fn = int((flagged & actual).sum()), int((flagged & ~actual).sum()), int((~flagged & actual).sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    seen = flagged | reviewed
    return {
        "positives": int(actual.sum()), "precision": precision, "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        "hits": tp, "false_alarms": fp, "review_share": float(np.mean(seen)),
        "reached": int((seen & actual).sum()), "reached_share": float((seen & actual).sum() / actual.sum()),
        "never_seen": int((~seen & actual).sum()), "avg_precision": float(average_precision_score(actual, score)),
    }


def pct(x):
    return f"{100 * x:.1f}%"


def table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" if i == 0 else "---:" for i in range(len(header))) + "|"]
    return out + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]


class Setup:
    """Everything computed once: votes, history, facts, triage scores with and without facts."""

    def __init__(self):
        self.rows = load_votes()
        self.by_key = {(r["meeting_id"], r["item_no"]): r for r in self.rows}
        self.index = build_history_index(self.rows)
        self.facts = company_facts()
        self.triage = {f: {y: score_year(self.rows, y, use_facts=f) for y in YEARS} for f in (True, False)}
        self.rule_states = chair_ceo_states(self.rows, self.facts)

    def scored(self, year, facts, combo):
        results = read(RUNS / f"results_{year}_history{WITH if facts else WITHOUT}.csv")
        p_model = np.array([self.triage[facts][year].scores[r["meeting_id"], r["item_no"]] for r in results])
        scores = np.array([combined_score(self.by_key[r["meeting_id"], r["item_no"]], float(r["p_mot"]), m, self.index, combo)
                           for r, m in zip(results, p_model)])
        dates = [self.by_key[r["meeting_id"], r["item_no"]]["meeting_date"] for r in results]
        return results, p_model, scores, dates

    def walk_forward(self, year, facts):
        """Recommendation and routing for one year, fitted on earlier years only."""
        combo = fit([y for y in YEARS if y < year], self.rows, tag=WITH if facts else WITHOUT, triage=self.triage[facts])
        results, p_model, scores, dates = self.scored(year, facts, combo)
        _, _, prev_scores, prev_dates = self.scored(year - 1, facts, combo)
        live = np.array(live_review(dates, scores, combo["review_share"], list(zip(prev_dates, prev_scores))))
        batch = scores >= review_cutoff(list(scores), combo["review_share"])
        jev = np.array([r["jev_vote"] == "MOT" for r in results]) & (p_model >= combo["model_flag"])
        rule = np.array([facts and self.rule_states.get((r["meeting_id"], r["item_no"])) == "active" for r in results])
        flagged = jev | rule
        skip_groups = safe_groups(self.rows, self.facts, f"{year}-01-01") if facts else set()
        safe = np.array([any(g in skip_groups for g in self.facts.groups(self.by_key[r["meeting_id"], r["item_no"]])) for r in results])
        actual = np.array([r["nbim_vote"] == "MOT" for r in results])
        return {"results": results, "scores": scores, "actual": actual, "combo": combo, "skip_groups": skip_groups,
                "flagged": flagged, "jev_flag": jev, "rule_flag": rule, "safe": safe, "live": live, "batch": batch,
                "reviewed": (live & ~safe) | flagged}


def row_metrics(w, reviewed=None, flagged=None):
    return metrics(w["flagged"] if flagged is None else flagged, w["reviewed"] if reviewed is None else reviewed, w["scores"], w["actual"])


def my_report(s, runs):
    lines = ["# Jev pipeline: walk-forward results with company facts", "",
             "Produced by `python src/report_results.py`, from saved Jev answers (no API calls).", "",
             "## How each year is scored", "",
             "- **Walk-forward.** The combination (weights, review share, model flag) is fitted on all earlier years with a Jev run, "
             "pooled. The triage model trains on earlier years only.",
             "- **Live review share.** Each proposal is ranked against the previous 12 months of scores, starting from last year's run, "
             "as a live system would. Nothing from later in the year is used.",
             "- **Recommendation:** MOT when Jev votes MOT and the triage model is at or above the flag, or when NBIM's rule 1.3.1 "
             "(a US nominee who is both CEO and chair) fires and its drift monitor still trusts it. Every recommended MOT goes to a person.",
             "- **Skip rule:** a group (proposal type, or nominee role in Japan, Korea or the US) skips review when NBIM opposed none of "
             "at least 100 such proposals in earlier years.",
             "- **Company facts**, all from documents filed before the meeting: Japan (EDINET annual reports: nominee role, board "
             "independence), US (main's reading of each proxy: nominee role, independence, chair, attendance; last year's vote results "
             "from SEC 8-K item 5.07; CEO pay), Korea (OpenDART: board composition, CEO also chair; nominee role from the ballot). "
             "They go to the triage model and into Jev's input.",
             "- **Target:** NBIM voted MOT. Abstentions count as not MOT.", "",
             "## Every test year", ""]
    out = []
    for year in TEST_YEARS:
        w = runs[(year, True)]
        m = row_metrics(w)
        board = np.array([r["mgmt_rec"] == "MOT" for r in w["results"]])
        jev = np.array([r["jev_vote"] == "MOT" for r in w["results"]])
        b, j = metrics(board, board, board, w["actual"]), metrics(jev, jev, jev, w["actual"])
        right = [r for r, f, a in zip(w["results"], w["flagged"], w["actual"]) if f and a and r["rationale_section"].startswith("GVG")]
        cited = sum(r["rationale_section"] == "GVG " + (r["mot_section"] or r["cited_section"]) for r in right)
        out.append([year, f"{min(w['combo']['fitted_on'])}-{max(w['combo']['fitted_on'])}", len(w["results"]), m["positives"],
                    pct(b["f1"]), pct(j["f1"]), pct(m["precision"]), pct(m["recall"]), f"**{pct(m['f1'])}**",
                    f"**{pct(m['review_share'])}**", f"{m['reached']} ({pct(m['reached_share'])})", f"{m['avg_precision']:.3f}", f"{cited}/{len(right)}"])
    lines += table(["Year", "Fitted on", "Proposals", "MOT", "Board F1", "Jev alone F1", "Precision", "Recall", "F1", "Review",
                    "MOT reaching a person", "AP combined", "Right section"], out)
    lines += ["", "2021 is not a test year: there is no earlier Jev year to fit on. 2019 and 2020 have no runs: the triage model needs two "
              "earlier years of votes.", "",
              "## What each piece adds", "",
              "Average over the test years. Each row adds one piece to the row above.", ""]
    steps = []
    for name, fn in (
        ("No company facts, ranked within the year", lambda y: row_metrics(runs[(y, False)], runs[(y, False)]["batch"] | runs[(y, False)]["flagged"])),
        ("+ live review share (previous 12 months)", lambda y: row_metrics(runs[(y, False)])),
        ("+ company facts in the model and in Jev's input", lambda y: row_metrics(runs[(y, True)], runs[(y, True)]["live"] | runs[(y, True)]["jev_flag"], runs[(y, True)]["jev_flag"])),
        ("+ chair-and-CEO rule with drift monitor", lambda y: row_metrics(runs[(y, True)], runs[(y, True)]["live"] | runs[(y, True)]["flagged"])),
        ("+ skip rule (the full system)", lambda y: row_metrics(runs[(y, True)])),
    ):
        ms = [fn(y) for y in TEST_YEARS]
        mean = lambda k: sum(m[k] for m in ms) / len(ms)
        steps.append([name, f"**{pct(mean('f1'))}**", pct(mean("precision")), pct(mean("recall")), f"**{pct(mean('review_share'))}**", pct(mean("reached_share"))])
    lines += table(["Setup", "F1", "Precision", "Recall", "Review", "MOT reaching a person"], steps)

    lines += ["", "## Skip rule", "", "Groups that skip review, learned from earlier years only:", ""]
    out = []
    for year in TEST_YEARS:
        w = runs[(year, True)]
        would = w["live"] & w["safe"] & ~w["flagged"]
        out.append([year, "; ".join(sorted(w["skip_groups"])) or "none yet", int(would.sum()), int((would & w["actual"]).sum())])
    lines += table(["Year", "Groups", "Proposals skipped", "MOT among them"], out)

    lines += ["", "## Chair-and-CEO rule (US, NBIM rule 1.3.1)", ""]
    out = []
    for year in TEST_YEARS:
        w = runs[(year, True)]
        fired = [(r, a) for r, a in zip(w["results"], w["actual"]) if (r["meeting_id"], r["item_no"]) in s.rule_states]
        active = [(r, a) for r, a in fired if s.rule_states[(r["meeting_id"], r["item_no"])] == "active"]
        out.append([year, len(fired), f"{sum(a for _, a in fired)}/{len(fired)}", len(active), f"{sum(a for _, a in active)}/{len(active)}"])
    lines += table(["Year", "Nominees who are CEO and chair", "NBIM MOT", "Rule active (monitor)", "MOT when active"], out)

    lines += ["", "## Coverage of the company facts", ""]
    cov = defaultdict(Counter)
    for year in TEST_YEARS:
        for r in runs[(year, True)]["results"]:
            row = s.by_key[r["meeting_id"], r["item_no"]]
            for kind, value in (("Japan director", s.facts.japan.for_row(row)), ("US director", s.facts.us_director(row)),
                                ("US pay vote", s.facts.us_pay(row)), ("Korea director", s.facts.korea_director(row))):
                if value is not None:
                    cov[kind]["proposals"] += 1
                    cov[kind]["found"] += bool(value.get("found"))
                    cov[kind]["mot"] += r["nbim_vote"] == "MOT"
    lines += table(["Proposals", "In test years", "With facts", "NBIM MOT"],
                   [[k, c["proposals"], f"{c['found']} ({pct(c['found'] / c['proposals'])})", c["mot"]] for k, c in cov.items()])
    lines += ["", "## What to keep in mind", "",
              "- **The design was chosen while looking at 2025 and 2026.** Walk-forward fitting removes tuning on the test year, but not that.",
              "- How each year was used: " + "; ".join(f"{y} {t}" for y, t in SEEN.items()) + ".",
              "- EDINET only keeps AGM vote results from mid-2024, so Japanese last-year support reaches 2025-26 only. US vote results "
              "go back to 2018.",
              "- US nominee facts come from main's AI reading of each proxy; their accuracy is main's, and is checked there.",
              "- Each MOT vote is 1-2 percentage points of recall, so small differences between years are noise.", ""]
    return lines


def key_text(r):
    return (r["meeting_date"], r["company"], r["proposal_text"])


def compare(s, runs, main_dir):
    votes = s.by_key
    csv_rows, by_year = [], {}
    for year in TEST_YEARS:
        w = runs[(year, True)]
        theirs = read(Path(main_dir) / "src" / "benchmark" / f"prediksjoner_{year}.csv")
        slots = defaultdict(list)
        for t in theirs:
            slots[key_text(t)].append(t)
        used, pairs = defaultdict(int), []
        for i, r in enumerate(w["results"]):
            k = key_text(r | {"meeting_date": votes[r["meeting_id"], r["item_no"]]["meeting_date"]})
            if used[k] < len(slots[k]):
                pairs.append((i, slots[k][used[k]]))
                used[k] += 1
        idx = np.array([i for i, _ in pairs])
        results = [w["results"][i] for i in idx]
        mot = w["actual"][idx]
        against = np.array([votes[r["meeting_id"], r["item_no"]]["against_board"] in ("1", "1.0") for r in results])
        board = np.array([r["mgmt_rec"] == "MOT" for r in results])
        systems = {
            "marie: Jev pipeline + facts": (w["flagged"][idx], w["reviewed"][idx], w["scores"][idx]),
            "main: history model": (np.array([t["band"] == "likely AGAINST board" for _, t in pairs]),
                                    np.array([t["band"] == "send to human" for _, t in pairs]),
                                    np.array([float(t["probability_against"]) for _, t in pairs])),
            "Follow the board": (board, np.zeros(len(results), bool), board.astype(float)),
        }
        if year == 2026:
            dec = {r["key"]: r for r in read(Path(main_dir) / "data" / "outputs" / "decisions_2026.csv") if r["dataset"] == "NBIM votes, all proposal types"}
            d = [dec[f"{r['meeting_id']}-{r['item_no']}"] for r in results]
            systems["main: full system (2026 only)"] = (np.array([x["suggested_vote"] in ("MOT", "AVSTÅ") for x in d]),
                                                        np.array([x["decided_by"] == "human review" for x in d]),
                                                        np.array([float(x["probability_against_board"]) for x in d]))
        by_year[year] = (len(results), mot, against, systems)
        for name, (flag, rev, score) in systems.items():
            for target, actual in (("NBIM voted MOT", mot), ("against the board", against)):
                csv_rows.append({"year": year, "system": name, "target": target, "proposals": len(results), **metrics(flag, rev, score, actual)})

    lines = ["# Comparison: marie's Jev pipeline (with company facts) and main's system", "",
             "Produced by `python src/report_results.py --main-dir <checkout of main>`. Same proposals for both systems every year "
             "(`data/dirty/real_votes.csv`). marie is scored walk-forward with a live review share. Full numbers in `comparison_with_main.csv`.", "",
             "main predicts **against the board**, marie predicts **NBIM voted MOT**. They differ on shareholder proposals and abstentions, "
             "so every number is shown for both targets.", "", "## Headline: average over 2022-2026", ""]
    out = []
    for target in ("NBIM voted MOT", "against the board"):
        for name in ("marie: Jev pipeline + facts", "main: history model", "Follow the board"):
            c = [x for x in csv_rows if x["system"] == name and x["target"] == target]
            mean = lambda k: sum(x[k] for x in c) / len(c)
            dash = name == "Follow the board"
            out.append([target, name, f"**{pct(mean('f1'))}**", pct(mean("precision")), pct(mean("recall")),
                        "–" if dash else pct(mean("review_share")), "–" if dash else pct(mean("reached_share")),
                        "–" if dash else f"{mean('avg_precision'):.3f}"])
    lines += table(["Target", "System", "F1", "Precision", "Recall", "Review", "Reaching a person", "Avg precision"], out)
    for target in ("NBIM voted MOT", "against the board"):
        lines += ["", f"## Year by year, target: {target}", ""]
        out = []
        for year in TEST_YEARS:
            for name in ("marie: Jev pipeline + facts", "main: history model", "main: full system (2026 only)", "Follow the board"):
                m = next((c for c in csv_rows if c["year"] == year and c["system"] == name and c["target"] == target), None)
                if m is None:
                    continue
                dash = name == "Follow the board"
                out.append([year, name, pct(m["precision"]), pct(m["recall"]), f"**{pct(m['f1'])}**", m["hits"], m["false_alarms"],
                            "–" if dash else pct(m["review_share"]), "–" if dash else f"{m['reached']}/{m['positives']} ({pct(m['reached_share'])})",
                            "–" if dash else m["never_seen"], "–" if dash else f"{m['avg_precision']:.3f}"])
        lines += table(["Year", "System", "Precision", "Recall", "F1", "Hits", "False alarms", "Review", "Reaching a person",
                        "Never seen", "Avg precision"], out)
    lines += ["", "## Same review effort", "",
              "Each system's ranking picks the same number of proposals for a person. Cells: MOT votes caught · against-the-board votes caught.", ""]
    out = []
    for year in TEST_YEARS:
        n, mot, against, systems = by_year[year]
        for share in (0.10, 0.25, 0.40):
            k = int(round(share * n))
            cells = [year, pct(share)]
            for name in ("marie: Jev pipeline + facts", "main: history model"):
                top = np.zeros(n, bool)
                top[np.argsort(-systems[name][2], kind="stable")[:k]] = True
                cells.append(f"{int((top & mot).sum())}/{int(mot.sum())} · {int((top & against).sum())}/{int(against.sum())}")
            out.append(cells)
    lines += table(["Year", "Reviewed", "marie", "main"], out)
    lines += ["", "## What to keep in mind", "",
              "- main's per-year numbers are its **history model** only. Its full system (director and board rules, a low-information "
              "gate, abstentions, AI proxy reading) is only saved for 2026. main's pay model scores a different file.",
              "- marie reuses main's AI proxy facts for US directors and main's CEO pay figures.",
              "- How marie's years were used while designing: " + "; ".join(f"{y} {t}" for y, t in SEEN.items()) + ".",
              "- With 60-110 positives a year, differences of a few votes are noise.", ""]
    return lines, csv_rows


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--main-dir", help="a checkout of main with its per-year predictions written")
    a = p.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    s = Setup()
    runs = {(y, f): s.walk_forward(y, f) for y in TEST_YEARS for f in (True, False)}
    (OUT / "jev_results.md").write_text("\n".join(my_report(s, runs)), encoding="utf-8")
    print(f"Wrote {(OUT / 'jev_results.md').relative_to(DATA.parent)}")
    if a.main_dir:
        lines, csv_rows = compare(s, runs, a.main_dir)
        (OUT / "comparison_with_main.md").write_text("\n".join(lines), encoding="utf-8")
        with open(OUT / "comparison_with_main.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(csv_rows[0]))
            w.writeheader()
            w.writerows({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()} for r in csv_rows)
        print(f"Wrote {(OUT / 'comparison_with_main.md').relative_to(DATA.parent)} and comparison_with_main.csv")


if __name__ == "__main__":
    main()
