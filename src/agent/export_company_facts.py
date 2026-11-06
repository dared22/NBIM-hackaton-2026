"""Export the company facts Marie's code attaches to each proposal (Japan EDINET, Korea OpenDART, US 8-K vote results).
Run in a checkout of branch marie:  python export_marie_facts.py <out_file>
Every fact comes from a document filed strictly before the meeting date (her company_facts.py). No votes of NBIM are written."""
import sys, csv
sys.path.insert(0, "src")
from company_facts import FEATURES, facts
from jev_mvp import load_votes
known = facts()
rows = load_votes()
with open(sys.argv[1], "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["meeting_id", "item_no", *FEATURES, "jp_nominee_title"])
    n = 0
    for r in rows:
        feats = known.features(r)
        if all(v == -1.0 for v in feats):
            continue
        jp = known.japan.for_row(r)
        w.writerow([r["meeting_id"], r["item_no"], *[("" if v == -1.0 else f"{v:g}") for v in feats],
                    (jp or {}).get("nominee_title") or ""])
        n += 1
print("rows with at least one fact:", n, "of", len(rows))
