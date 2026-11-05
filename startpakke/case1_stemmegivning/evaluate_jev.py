"""Compare Jev with voting as the board recommends, using saved run results.

Thresholds are only ever chosen on the development year and then applied unchanged
to the holdout year, so the holdout numbers are not tuned on the holdout.

    python evaluate_jev.py --dev 2025                  # choose level and thresholds
    python evaluate_jev.py --dev 2025 --test 2026 --level history   # final comparison
    python evaluate_jev.py --dev 2025 --test 2026 --level history --tag _v2  # the clean holdout
    python evaluate_jev.py --dev 2025 --tag ""         # the saved runs of the first design

The human-review band is:
    p(MOT) >= high         recommend MOT automatically
    low <= p(MOT) < high   send to a person
    p(MOT) < low           recommend the board's position automatically
"""

import argparse
import csv
import random
from pathlib import Path

RUNS = Path(__file__).parent / "jev_runs"
LEVELS = ("proposal", "rules", "history", "def14a")
TARGET_RECALL = 0.9  # low: the review band should keep at least this share of MOT votes.
TARGET_PRECISION = 0.8  # high: automatic MOT should be right at least this often.


def load(year, level, tag):
    path = RUNS / f"results_{year}_{level}{tag}.csv"
    if not path.exists():
        return None
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["p_mot"] = float(r["p_mot"])
        r["actual"] = r["nbim_vote"] == "MOT"
        r["jev_vote"] = r.get("jev_vote", r["vote"])  # In earlier runs, vote was Jev's own.
    return rows


def metrics(predicted, actual):
    tp = sum(p and a for p, a in zip(predicted, actual))
    fp = sum(p and not a for p, a in zip(predicted, actual))
    fn = sum(a and not p for p, a in zip(predicted, actual))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}


def show(name, m):
    print(f"{name:42s} precision {m['precision']:6.1%}  recall {m['recall']:6.1%}  F1 {m['f1']:6.1%}  hits {m['tp']:4d}  false alarms {m['fp']:4d}  missed {m['fn']:4d}")


def average_precision(scores, actual):
    """Threshold-free: how well the score ranks MOT votes first. Equals the base rate if it cannot."""
    positives, hits, total = sum(actual), 0, 0.0
    ranked = sorted(zip(scores, actual), key=lambda x: -x[0])
    i = 0
    while i < len(ranked):
        j = i
        while j < len(ranked) and ranked[j][0] == ranked[i][0]:
            j += 1
        new_hits = sum(a for _, a in ranked[i:j])
        hits += new_hits
        total += new_hits / positives * (hits / j)
        i = j
    return total


def grid(rows):
    return sorted({r["p_mot"] for r in rows})


def best_f1_threshold(rows):
    actual = [r["actual"] for r in rows]
    return max(grid(rows), key=lambda t: (metrics([r["p_mot"] >= t for r in rows], actual)["f1"], t))


def review_band(rows):
    """Thresholds from the targets above, on this set of rows."""
    actual = [r["actual"] for r in rows]
    low = max((t for t in grid(rows) if metrics([r["p_mot"] >= t for r in rows], actual)["recall"] >= TARGET_RECALL), default=0.0)
    high = next((t for t in grid(rows) if t >= low and metrics([r["p_mot"] >= t for r in rows], actual)["precision"] >= TARGET_PRECISION), None)
    return low, high


def f1_difference_ci(rows, threshold, draws=2000, seed=42):
    """Bootstrap over meetings, since votes in one meeting are not independent."""
    meetings = {}
    for r in rows:
        meetings.setdefault(r["meeting_id"], []).append(r)
    ids = sorted(meetings)
    rng = random.Random(seed)
    diffs, recalls = [], []
    for _ in range(draws):
        sample = [r for m in rng.choices(ids, k=len(ids)) for r in meetings[m]]
        actual = [r["actual"] for r in sample]
        jev = metrics([r["p_mot"] >= threshold for r in sample], actual)
        board = metrics([r["mgmt_rec"] == "MOT" for r in sample], actual)
        diffs.append(jev["f1"] - board["f1"])
        recalls.append(jev["recall"] - board["recall"])
    def interval(values):
        values = sorted(values)
        return values[int(0.025 * draws)], values[int(0.975 * draws)]
    return interval(diffs), interval(recalls)


def show_routing(rows, actual):
    """What the pipeline itself recommended and routed."""
    print("\nThe pipeline as run:")
    show("  Recommendation", metrics([r["vote"] == "MOT" for r in rows], actual))
    automatic = [r["vote"] == "MOT" and r["route"] == "automatic" for r in rows]
    reviewed = [r["route"] == "human_review" for r in rows]
    show("  Automatic MOT only", metrics(automatic, actual))
    show("  Automatic + all reviews caught", metrics([a or b for a, b in zip(automatic, reviewed)], actual))
    print(f"  People review {sum(reviewed)} of {len(rows)} ({sum(reviewed) / len(rows):.1%}), containing {sum(r and a for r, a in zip(reviewed, actual))} MOT votes.")
    checkable = [r for r in rows if r["vote"] == "MOT" and r["actual"] and r["rationale_section"].startswith("GVG")]
    right = sum(r["rationale_section"] == f"GVG {r['cited_section']}" for r in checkable)
    print(f"  Section NBIM cited, named by the pipeline: {right} of {len(checkable)} correct MOT recommendations.")


def report(rows, threshold, band, title):
    actual = [r["actual"] for r in rows]
    print(f"\n=== {title}: {len(rows)} proposals in {len({r['meeting_id'] for r in rows})} meetings, {sum(actual)} MOT ===")
    board = metrics([r["mgmt_rec"] == "MOT" for r in rows], actual)
    show("Baseline: vote as the board recommends", board)
    show("Always FOR", metrics([False] * len(rows), actual))
    show(f"Jev: p(MOT) >= {threshold:.2f}", metrics([r["p_mot"] >= threshold for r in rows], actual))
    show("Jev: its own top choice", metrics([r["jev_vote"] == "MOT" for r in rows], actual))
    print(f"\nAverage precision: Jev {average_precision([r['p_mot'] for r in rows], actual):.3f}", end="")
    if rows[0].get("p_model"):
        model = [float(r["p_model"]) for r in rows]
        print(f", triage model {average_precision(model, actual):.3f}. Base rate {sum(actual) / len(rows):.3f}.")
        show_routing(rows, actual)
    else:
        print(f". Base rate {sum(actual) / len(rows):.3f}.")

    agree = sum((r["mgmt_rec"] == r["nbim_vote"]) for r in rows) / len(rows)
    print(f"\nBaseline agreement on all three options: {agree:.1%} (the misleading number).")
    key = [r for r in rows if r["mgmt_rec"] == "FOR" and r["actual"]]
    found = sum(r["p_mot"] >= threshold for r in key)
    print(f"Board FOR, NBIM MOT (the cases the baseline can never find): Jev finds {found} of {len(key)}.")

    low, high = band
    if high is None:
        print(f"\nReview band: no threshold reached {TARGET_PRECISION:.0%} precision on development data.")
        high = float("inf")
    auto_mot = [r["p_mot"] >= high for r in rows]
    review = [low <= r["p_mot"] < high for r in rows]
    print(f"\nReview band from development data: low {low:.2f}, high {high:.2f}")
    show("  Automatic MOT only", metrics(auto_mot, actual))
    show("  Automatic MOT + all reviews caught", metrics([a or b for a, b in zip(auto_mot, review)], actual))
    print(f"  People review {sum(review)} of {len(rows)} proposals ({sum(review) / len(rows):.1%}), containing {sum(r and a for r, a in zip(review, actual))} of {sum(actual)} MOT votes.")
    print(f"  Automatic and not reviewed: {len(rows) - sum(review) - sum(auto_mot)} proposals as the board's position, of which {sum(a and not r and not m for a, r, m in zip(actual, review, auto_mot))} were really MOT.")

    (f1_low, f1_high), (rec_low, rec_high) = f1_difference_ci(rows, threshold)
    print(f"\n95% interval, Jev minus baseline, by meeting: F1 {f1_low:+.1%} to {f1_high:+.1%}; recall {rec_low:+.1%} to {rec_high:+.1%}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dev", type=int, required=True)
    p.add_argument("--test", type=int)
    p.add_argument("--level", choices=LEVELS)
    p.add_argument("--tag", default="_v3", help="suffix of the result files. _v2 is the clean 2026 holdout, \"\" the first design")
    a = p.parse_args()

    levels = [a.level] if a.level else [l for l in LEVELS if load(a.dev, l, a.tag)]
    if not levels:
        raise SystemExit(f"No full runs for {a.dev} with tag '{a.tag}'.")
    for level in levels:
        dev = load(a.dev, level, a.tag)
        if dev is None:
            raise SystemExit(f"No full run for {a.dev} at level {level}.")
        threshold, band = best_f1_threshold(dev), review_band(dev)
        report(dev, threshold, band, f"DEVELOPMENT {a.dev}, level {level} (tuned here, optimistic)")
        if a.test:
            test = load(a.test, level, a.tag)
            if test is None:
                raise SystemExit(f"No full run for {a.test} at level {level}.")
            note = "design chosen after this holdout was seen" if a.tag == "_v3" else f"thresholds fixed on {a.dev}"
            report(test, threshold, band, f"HOLDOUT {a.test}, level {level} ({note})")


if __name__ == "__main__":
    main()
