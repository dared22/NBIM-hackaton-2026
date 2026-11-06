"""CSV decisions and dashboard exports."""

import csv
import json
import os
import re
from dataclasses import astuple
from pathlib import Path

from src import data as paths
from src.data import COLUMNS as COLS
from src.evidence import rule_check as rc

YEAR = 2026

COMPONENTS = paths.COMPONENTS_2026

DOCUMENTS = paths.DOCUMENTS

COLUMNS = [
    "year",
    "meeting_date",
    "meeting_id",
    "item_no",
    "company_id",
    "company",
    "country",
    "market",
    "proposal_text",
    "proposal_type",
    "proponent",
    "mgmt_rec",
    "vote",
    "confidence",
    "confidence_basis",
    "confidence_raw",
    "p_combined",
    "p_mot",
    "p_model",
    "route",
    "review_reason",
    "citation",
    "citation_source",
    "guideline_text",
    "guideline_edition",
    "reasons",
    "passages",
    "evidence_url",
    "document_url",
    "document_label",
    "documents",
    "nbim_vote",
    "rationale_section",
    "rationale_text",
]

CODES = (
    ("security flag", "instruction_in_text"),
    ("a rule applies but", "rule_needs_person"),
    ("rule suspended", "rule_needs_person"),
    ("low information", "low_confidence"),
)

BASIS = (
    "kombinert modell (main): stemmehistorikk, Jev, en andre modell, NBIMs regler og selskapsfakta"
)


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
    m = re.search(r"GVG (\d+\.\d+(?:-AT)?(?:\.\d+)?)", guide) or re.search(
        r"\b(\d+\.\d+(?:-AT)?\.\d+)\b", guide
    )
    if not m:
        return "", "", ""
    source = (
        "rule in code"
        if d["model"].startswith("NBIM rule")
        else "Jev"
        if "Jev decision model" in guide
        else "rule check model"
        if "rule check" in guide
        else "NBIM's usual reason for this proposal type"
    )
    return m.group(1), source, d["guideline_text"]


def common_fields(decision: dict) -> dict:
    """Fields derived from each serialized decision."""
    p = float(decision["probability_against_board"])
    against = decision["suggested_vote"] != decision["board_recommendation"]
    confidence = round(p if against else 1 - p, 4)
    reasons = [
        line
        for line in ([decision["review_reason"]] if decision["review_reason"] else [])
        + decision["reasons"].split(" | ")
        if line
    ]
    return {
        "year": YEAR,
        "meeting_date": decision["meeting_date"],
        "company": decision["company"],
        "proposal_text": decision["proposal"],
        "mgmt_rec": decision["board_recommendation"],
        "vote": decision["suggested_vote"],
        "confidence": confidence,
        "confidence_raw": confidence,
        "p_combined": round(p, 4),
        "route": "human_review" if decision["decided_by"] == "human review" else "automatic",
        "review_reason": review_codes(decision["review_reason"]),
        "guideline_edition": "2025",
        "reasons": " | ".join(reasons),
        "passages": "{}",
        "nbim_vote": decision["actual_vote"],
    }


def export_dashboard(output_dir):
    decisions_path = os.path.join(output_dir, "decisions_2026.csv")
    out = os.path.join(output_dir, "dashboard", "predictions_main.csv")
    with open(rc.GUIDELINES, encoding="utf-8") as f:
        principle = next(p["tekst"] for p in json.load(f)["prinsipper"] if p["id"] == "P.1")
    with open(rc.VOTES, encoding="utf-8-sig", newline="") as f:
        votes = {f"{r['meeting_id']}-{r['item_no']}": r for r in csv.DictReader(f)}
    with open(COMPONENTS, encoding="utf-8", newline="") as f:
        comp = {f"{r['meeting_id']}-{r['item_no']}": r for r in csv.DictReader(f)}
    jev = {k: r["jev_p_mot"] for k, r in comp.items()}
    with open(decisions_path, encoding="utf-8", newline="") as f:
        decisions = [d for d in csv.DictReader(f) if d["dataset"].startswith("NBIM votes")]
    with open(DOCUMENTS, encoding="utf-8", newline="") as f:
        filed = {f"{r['meeting_id']}-{r['item_no']}": r for r in csv.DictReader(f)}
    rows = []
    for d in decisions:
        v = votes[d["key"]]
        against = d["suggested_vote"] != d["board_recommendation"]
        section, source, words = citation(d)
        if not section and not against:
            section, source, words = (
                "P.1",
                "voting principle",
                "Voting principle (not a numbered guideline): " + principle,
            )
        url, label = d["evidence_url"], "Selskapets dokument hos SEC" if d["evidence_url"] else ""
        documents = (
            [{"label": label, "url": url, "filed": "før møtet", "about": "kilde for faktaene"}]
            if url
            else []
        )
        doc = filed.get(d["key"])
        if doc:
            documents += [x for x in json.loads(doc["documents"]) if x.get("url") != url]
            url, label = url or doc["document_url"], label or doc["document_label"]
        rows.append(
            {
                **common_fields(d),
                "meeting_id": v["meeting_id"],
                "item_no": v["item_no"],
                "company_id": v.get("company_id", ""),
                "country": v.get("country", ""),
                "market": v.get("market", ""),
                "proposal_type": v.get("proposal_type", ""),
                "proponent": v.get("proponent", ""),
                "confidence_basis": BASIS,
                "p_mot": jev.get(d["key"], ""),
                "p_model": comp[d["key"]]["triage_p"] if d["key"] in comp else "",
                "citation": section,
                "citation_source": source,
                "guideline_text": words,
                "evidence_url": d["evidence_url"],
                "document_url": url,
                "document_label": label,
                "documents": json.dumps(documents, ensure_ascii=False),
                "rationale_section": v.get("rationale_section", ""),
                "rationale_text": v.get("rationale_text", ""),
            }
        )
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def write_outputs(general, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "decisions_2026.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLS)
        writer.writerows(
            astuple(d) for d in sorted(general, key=lambda d: -float(d.probability_against_board))
        )
    export_dashboard(output_dir)
    print(console_tables(general))
    print(f"\nWrote predictions to {output_dir}")


def format_table(headers: list[str], rows: list[list[str]]) -> str:
    """Compact terminal table with right-aligned numbers."""
    widths = [max(len(row[i]) for row in [headers, *rows]) for i in range(len(headers))]

    def border(left, middle, right):
        return left + middle.join("─" * (width + 2) for width in widths) + right

    def line(row):
        cells = [
            str(cell).ljust(widths[i]) if i == 0 else str(cell).rjust(widths[i])
            for i, cell in enumerate(row)
        ]
        return "│ " + " │ ".join(cells) + " │"

    return "\n".join(
        [
            border("┌", "┬", "┐"),
            line(headers),
            border("├", "┼", "┤"),
            *(line(row) for row in rows),
            border("└", "┴", "┘"),
        ]
    )


def console_tables(decisions: list) -> str:
    """Summarize already computed predictions without fitting or generating reports."""
    from src.models.history import read_votes
    from src.models.scoring import prf

    votes = read_votes(paths.VOTES)
    previous = {
        (r["company_id"], r["text_key"]): r["nbim_vote"]
        for r in votes
        if r["meeting_date"] < f"{YEAR}-01-01"
    }
    by_key = {f"{r['meeting_id']}-{r['item_no']}": r for r in votes}
    repeated = []
    for decision in decisions:
        row = by_key.get(decision.key)
        last = (
            previous.get((row["company_id"], row["text_key"]), decision.board_recommendation)
            if row
            else decision.board_recommendation
        )
        repeated.append(last == "MOT")
    actual = [d.actual_vote == "MOT" for d in decisions]
    methods = [
        ("All suggestions", [d.suggested_vote == "MOT" for d in decisions]),
        (
            "Automatic only",
            [d.suggested_vote == "MOT" and d.decided_by == "automatic" for d in decisions],
        ),
        ("Follow board", [d.board_recommendation == "MOT" for d in decisions]),
        ("Repeat last vote", repeated),
    ]
    quality = []
    for name, predicted in methods:
        precision, recall, f1, tp, fp, fn = prf(predicted, actual)
        quality.append(
            [
                name,
                str(sum(predicted)),
                str(tp),
                str(fp),
                str(fn),
                f"{precision:.1%}",
                f"{recall:.1%}",
                f"{f1:.1%}",
            ]
        )
    routing = []
    for label, route in [("Automatic", "automatic"), ("Human review", "human review")]:
        group = [d for d in decisions if d.decided_by == route]
        share = len(group) / len(decisions) if decisions else 0
        routing.append(
            [
                label,
                f"{len(group):,}",
                f"{share:.1%}",
                str(sum(d.actual_vote == "MOT" for d in group)),
            ]
        )
    return "\n\n".join(
        [
            f"{YEAR} predictions · {len(decisions):,} proposals",
            "MOT vote quality\n"
            + format_table(
                ["Method", "Pred. MOT", "TP", "FP", "FN", "Precision", "Recall", "F1"], quality
            ),
            "Review routing\n"
            + format_table(["Route", "Proposals", "Share", "Actual MOT"], routing),
        ]
    )
