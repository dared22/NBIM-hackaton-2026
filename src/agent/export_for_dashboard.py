"""Main's decisions for the test year, in the column layout of the team's demo (branch marie, src/dashboard.py).

Run from the repo root, after python3 src/run.py (no internet, no API key):
    python3 src/agent/export_for_dashboard.py

Why
    The demo on branch marie reads data/outputs/dashboard/predictions_*.csv, made by that
    branch's own pipeline. This writes the decisions of the model described in
    docs/model-card.md in the same columns, so the demo can show the same model as the
    report. To use it on that branch, copy the file to data/outputs/dashboard/ and add one
    entry to FILES in src/dashboard.py:
        "Kombinert modell (main)": DATA / "predictions_main.csv"

What is and is not carried over
    - One row per proposal in NBIM's vote file for the test year (not the separate SEC pay file).
    - vote, route, probability, reasons, cited guideline with its words, link to the evidence.
    - The demo's review codes are fewer than main's reasons for review. Each reason is mapped
      to the nearest code; the full reason is kept as the first line of `reasons`.
    - `confidence` is the probability of the suggested vote: 1 - p when the tool follows the
      board, p when it suggests voting against.
    - Where main cites no guideline it follows the board, which is NBIM's first voting
      principle (P.1); that principle is shown, as the demo does for its own rows.
    - Not checked inside the running demo. The column names, the codes and the JSON fields
      are checked against the demo's own file format by tests/test_agent.py.
"""

import csv
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "src", "agent"))
import rule_check as rc  # noqa: E402

YEAR = 2026
DECISIONS = os.path.join(ROOT, "data", "outputs", f"decisions_{YEAR}.csv")
COMPONENTS = os.path.join(ROOT, "data", "evidence", "jev_pipeline", f"components_{YEAR}.csv")
OUT = os.path.join(ROOT, "data", "outputs", "dashboard", "predictions_main.csv")
COLUMNS = ["year", "meeting_date", "meeting_id", "item_no", "company_id", "company", "country", "market", "proposal_text",
           "proposal_type", "proponent", "mgmt_rec", "vote", "confidence", "confidence_basis", "confidence_raw", "p_combined",
           "p_mot", "p_model", "route", "review_reason", "citation", "citation_source", "guideline_text", "guideline_edition",
           "reasons", "passages", "evidence_url", "document_url", "document_label", "documents", "nbim_vote",
           "rationale_section", "rationale_text"]
CODES = (("security flag", "instruction_in_text"), ("a rule applies but", "rule_needs_person"), ("rule suspended", "rule_needs_person"),
         ("low information", "low_confidence"))
BASIS = "kombinert modell (main): stemmehistorikk, Jev, en andre modell, NBIMs regler og selskapsfakta"


def review_codes(reason):
    """The demo's codes for main's reasons for review. Anything without a code of its own is 'review_band'."""
    codes = []
    for part in [p for p in reason.split("; ") if p]:
        code = next((c for start, c in CODES if part.startswith(start)), "review_band")
        if code not in codes:
            codes.append(code)
    return ";".join(codes)


def citation(d):
    """(section, source, words) of the guideline a decision cites."""
    guide = d["guideline"]
    m = re.search(r"GVG (\d+\.\d+(?:-AT)?(?:\.\d+)?)", guide) or re.search(r"\b(\d+\.\d+(?:-AT)?\.\d+)\b", guide)
    if not m:
        return "", "", ""
    source = ("rule in code" if d["model"].startswith("NBIM rule") else "Jev" if "Jev decision model" in guide
              else "rule check model" if "rule check" in guide else "NBIM's usual reason for this proposal type")
    return m.group(1), source, d["guideline_text"]


def main():
    with open(rc.GUIDELINES, encoding="utf-8") as f:
        principle = next(p["tekst"] for p in json.load(f)["prinsipper"] if p["id"] == "P.1")
    with open(rc.VOTES, encoding="utf-8-sig", newline="") as f:
        votes = {f"{r['meeting_id']}-{r['item_no']}": r for r in csv.DictReader(f)}
    with open(COMPONENTS, encoding="utf-8", newline="") as f:
        jev = {f"{r['meeting_id']}-{r['item_no']}": r["jev_p_mot"] for r in csv.DictReader(f)}
    with open(DECISIONS, encoding="utf-8", newline="") as f:
        decisions = [d for d in csv.DictReader(f) if d["dataset"].startswith("NBIM votes")]
    rows = []
    for d in decisions:
        v = votes[d["key"]]
        p = float(d["probability_against_board"])
        against = d["suggested_vote"] != d["board_recommendation"]
        section, source, words = citation(d)
        if not section and not against:
            section, source, words = "P.1", "voting principle", "Voting principle (not a numbered guideline): " + principle
        reasons = [x for x in ([d["review_reason"]] if d["review_reason"] else []) + d["reasons"].split(" | ") if x]
        url = d["evidence_url"]
        documents = [{"label": "Selskapets dokument hos SEC", "url": url, "filed": "før møtet", "about": "kilde for faktaene"}] if url else []
        rows.append({
            "year": YEAR, "meeting_date": d["meeting_date"], "meeting_id": v["meeting_id"], "item_no": v["item_no"],
            "company_id": v.get("company_id", ""), "company": d["company"], "country": v.get("country", ""), "market": v.get("market", ""),
            "proposal_text": d["proposal"], "proposal_type": v.get("proposal_type", ""), "proponent": v.get("proponent", ""),
            "mgmt_rec": d["board_recommendation"], "vote": d["suggested_vote"],
            "confidence": round(p if against else 1 - p, 4), "confidence_basis": BASIS, "confidence_raw": round(p if against else 1 - p, 4),
            "p_combined": round(p, 4), "p_mot": jev.get(d["key"], ""), "p_model": round(p, 4),
            "route": "human_review" if d["decided_by"] == "human review" else "automatic",
            "review_reason": review_codes(d["review_reason"]), "citation": section, "citation_source": source,
            "guideline_text": words, "guideline_edition": "2025", "reasons": " | ".join(reasons), "passages": "{}",
            "evidence_url": url, "document_url": url, "document_label": "Selskapets dokument hos SEC" if url else "",
            "documents": json.dumps(documents, ensure_ascii=False), "nbim_vote": d["actual_vote"],
            "rationale_section": v.get("rationale_section", ""), "rationale_text": v.get("rationale_text", ""),
        })
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    mot = [r for r in rows if r["nbim_vote"] == "MOT"]
    said = [r for r in rows if r["vote"] == "MOT"]
    hit = sum(1 for r in said if r["nbim_vote"] == "MOT")
    print(f"Wrote {os.path.relpath(OUT, ROOT)}: {len(rows)} proposals for {YEAR}.")
    print(f"As the demo counts it (suggested MOT against NBIM's MOT votes, whoever decides): {len(said)} suggested, {hit} right "
          f"(precision {hit / len(said):.0%}, recall {hit / len(mot):.0%}); "
          f"{sum(1 for r in mot if r['route'] == 'human_review')} of {len(mot)} MOT votes are in the review pile.")


if __name__ == "__main__":
    main()
