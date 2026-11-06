"""Build the data the dashboard shows: every proposal 2022-2026, recommended walk-forward, with its reasons.

Run from the repository root (no API calls: Jev's answers come from the saved runs; a few minutes):
    python src/dashboard_data.py

Writes data/outputs/dashboard/predictions_jev.csv (with Jev) and predictions_nojev.csv (without Jev).
Each year is scored as in the evaluation (report_results.py): fitted on earlier years only, ranked against
the previous 12 months, with the director rules, the skip rule, code citations and the signals for where
"MOT" and "against the board" differ. The recommendation is checked against the evaluation's own.

NBIM's actual vote and rationale are added after the recommendation, as the answer key, so the dashboard
can show how the system did. They are never used to make a recommendation.
"""

import csv
import json

from against_board import Signals
from confidence import Calibrator
from demo import vote_confidence
from director_rules import deciding_rule
from director_rules import needs_person as rule_needs_person
from explain import explain, fact_reasons
from jev_mvp import DATA, candidate_rules, decide, guidelines_for, has_instruction, model_answers
import report_results as rr

OUT = DATA / "outputs" / "dashboard"
COLUMNS = ["year", "meeting_date", "meeting_id", "item_no", "company_id", "company", "country", "market", "proposal_text", "proposal_type",
           "proponent", "mgmt_rec", "vote", "confidence", "confidence_basis", "confidence_raw", "p_combined", "p_mot", "p_model", "route", "review_reason",
           "citation", "citation_source", "guideline_text", "guideline_edition", "reasons", "passages", "evidence_url",
           "document_url", "document_label", "documents",
           "nbim_vote", "rationale_section", "rationale_text"]


def saved_answers(r):
    """Jev's saved answer in the shape decide() reads (no API call)."""
    p_mot = float(r["p_mot"])
    return {"vote": {"choice": r["jev_vote"], "probabilities": {"FOR": 1 - p_mot, "MOT": p_mot, "AVSTÅ": 0.0},
                     "confidence": float(r["confidence"] or 0)}}


def build(s, year, jev):
    w = s.walk_forward(year, True, jev=jev)
    flag = w["combo"]["model_flag"]
    citer, differ = s.citers[year], Signals(s.rows, f"{year}-01-01")
    out, mismatched = [], 0
    for i, saved in enumerate(w["results"]):
        key = (saved["meeting_id"], saved["item_no"])
        row = s.by_key[key]
        edition, by_section = guidelines_for(row["meeting_date"], s.versions)
        rules = candidate_rules(row["proposal_type"], by_section)
        signals = w["signals"][i]
        facts_text = " ".join(fact_reasons(row, s.facts)[0])
        answers = saved_answers(saved) if jev else model_answers(w["p_model"][i], flag)
        found = has_instruction(row["proposal_text"])
        d = decide(answers, rules, row["mgmt_rec"], "history", p_model=float(w["p_model"][i]),
                   in_review_share=bool(w["live"][i] and not w["safe"][i]), instruction_found=found, model_flag=flag,
                   rule_mot=deciding_rule(signals), rule_review=rule_needs_person(signals),
                   cite=lambda vote: citer.cite(row, vote, by_section, s.index, signals, facts_text),
                   support=differ.support(row)[0], abstain=differ.abstain(row)[0])
        mismatched += d["vote"] != w["votes"][i] or (d["route"] == "human_review") != bool(w["reviewed"][i])
        why = explain(row, d, rules, edition, s.index, s.facts, signals, found, differ)
        score = float(w["scores"][i])
        docs = s.facts.meeting_documents(row)
        out.append({
            "year": year, "meeting_date": row["meeting_date"], "meeting_id": row["meeting_id"], "item_no": row["item_no"],
            "company_id": row["company_id"], "company": row["company"], "country": row["country"], "market": row["market"],
            "proposal_text": row["proposal_text"], "proposal_type": row["proposal_type"], "proponent": row["proponent"],
            "mgmt_rec": row["mgmt_rec"], "vote": d["vote"], "confidence": round(vote_confidence(d["vote"], score), 4),
            "confidence_raw": round(vote_confidence(d["vote"], score), 4), "confidence_basis": "",
            "p_combined": round(score, 4), "p_mot": "" if d["p_mot"] == "" else round(float(d["p_mot"]), 4),
            "p_model": round(float(w["p_model"][i]), 4), "route": d["route"], "review_reason": d["review_reason"],
            "citation": d["citation"], "citation_source": d["citation_source"], "guideline_text": why["guideline_text"],
            "guideline_edition": edition, "reasons": why["reasons"], "evidence_url": why["evidence_url"],
            "passages": json.dumps(why["passages"], ensure_ascii=False),
            # Every input document filed before the meeting; the first is the main one (the notice or annual report).
            "document_url": docs[0]["url"] if docs else "", "document_label": docs[0]["label"] if docs else "",
            "documents": json.dumps(docs, ensure_ascii=False),
            # The answer key, joined in after the recommendation.
            "nbim_vote": row["nbim_vote"], "rationale_section": row["rationale_section"], "rationale_text": row["rationale_text"],
        })
    return out, mismatched


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    s = rr.Setup()
    for jev in (True, False):
        rows = []
        for year in rr.TEST_YEARS:
            built, mismatched = build(s, year, jev)
            # Confidence: how often similar recommendations were right, from earlier years only (confidence.py).
            calibrate = Calibrator([r for r in rows if r["year"] < year])
            for r in built:
                c, basis = calibrate(r["vote"], r["mgmt_rec"], r["p_combined"])
                r["confidence"], r["confidence_basis"] = round(c, 4), basis
            rows += built
            print(f"{'with' if jev else 'without'} Jev, {year}: {len(built)} proposals"
                  + (f"; {mismatched} differ from the evaluation" if mismatched else ""))
        path = OUT / f"predictions_{'jev' if jev else 'nojev'}.csv"
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
