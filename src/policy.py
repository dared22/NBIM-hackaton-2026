"""Retrieve relevant NBIM policy rules without making the final vote."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GUIDELINES = (
    ROOT / "startpakke" / "case1_stemmegivning" / "retningslinjer_2025.json"
)
PROPOSAL_POLICY_TYPES: dict[str, tuple[str, ...]] = {
    "DIRECTOR_ELECTION": ("styrevalg", "styreleder_ceo"),
    "DIRECTOR_PAY": ("lonn",),
    "SAY_ON_PAY": ("lonn",),
    "SAY_ON_PAY_FREQ": ("lonn",),
    "AUDITOR": ("revisor",),
    "FIN_STATEMENTS": ("regnskap",),
    "DISCHARGE": ("ansvarsfrihet",),
    "DIVIDEND": ("generalforsamling",),
    "EQUITY_PLAN": ("lonn", "aksjeemisjon"),
    "SHARE_ISSUANCE": ("aksjeemisjon", "stemmerett"),
    "SHARE_REPURCHASE": ("aksjeemisjon", "stemmerett"),
    "RPT": ("narstaende", "transaksjon"),
    "MERGER": ("transaksjon", "oppkjopsvern"),
    "ARTICLES": ("vedtekter",),
    "ROUTINE": ("generalforsamling",),
}

TERM_GROUPS: tuple[tuple[str, ...], ...] = (
    ("ceo", "chief executive", "chief executive officer"),
    ("chairperson", "chairman", "board chair", "chair of the board"),
    ("independent", "independence", "non-independent", "non-independent director"),
    ("audit committee", "remuneration committee", "committee member"),
    ("diversity", "gender"),
    ("remuneration", "compensation", "salary", "pay", "bonus", "executive pay"),
    ("auditor", "auditors", "audit committee", "audit firm", "accounting"),
    ("share issue", "share issuance", "equity", "issuance", "authorisation", "authorization"),
    ("related party", "related parties", "related-party", "transaction", "transactions"),
    ("takeover", "takeovers", "anti-takeover", "acquisition", "acquisitions", "defensive measure"),
    ("shareholder", "shareholders", "voting rights", "vote", "votes", "voting"),
    ("attendance", "attended", "board meetings"),
    ("board", "director", "directors", "nomination committee"),
    ("dividend", "dividends", "distribution", "distributions"),
    ("financial statement", "financial statements", "accounts", "annual report", "annual reports"),
    ("sustainability", "climate", "emission", "emissions", "human rights"),
)
def _normalise(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold().replace("-", " ")).strip()


def load_guidelines(path: str | Path = DEFAULT_GUIDELINES) -> dict[str, Any]:
    """Load and validate the structured guideline document."""
    with Path(path).open(encoding="utf-8") as file:
        document = json.load(file)
    if not isinstance(document.get("regler"), list):
        raise ValueError("Guidelines JSON must contain a 'regler' list.")
    return document


def _section_context(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(section["id"]): section
        for section in document.get("underseksjoner", [])
        if isinstance(section, dict) and "id" in section
    }


def _market_matches(rule_market: str, market: str | None) -> bool:
    if not market or rule_market == "alle":
        return True
    normalised = _normalise(market)
    if normalised in {"dm", "developed", "utviklede"}:
        return rule_market.startswith("utviklede")
    if normalised in {"em", "emerging", "fremvoksende"}:
        return rule_market.startswith("fremvoksende")
    return True


def _market_label(value: str) -> str:
    return {
        "alle": "all markets",
        "utviklede": "developed markets",
        "fremvoksende": "emerging markets",
    }.get(value, value)


def _matched_terms(text: str) -> list[str]:
    normalised = _normalise(text)
    return [
        group[0]
        for group in TERM_GROUPS
        if any(
            re.search(
                rf"\b{re.escape(_normalise(term))}\b",
                normalised,
            )
            for term in group
        )
    ]


def find_candidate_rules(
    proposal_type: str,
    proposal_text: str,
    market: str | None,
    guidelines: dict[str, Any],
    company: str = "",
    country: str = "",
    top_k: int = 5,
) -> dict[str, Any]:
    """Return candidate rules; this function does not decide the vote."""
    if top_k < 1:
        raise ValueError("top_k must be positive.")

    policy_types = set(PROPOSAL_POLICY_TYPES.get(proposal_type, ()))
    text_terms = _matched_terms(proposal_text)
    sections = _section_context(guidelines)
    scored: list[tuple[int, dict[str, Any]]] = []

    for rule in guidelines["regler"]:
        derived = rule.get("avledet", {})
        rule_types = set(derived.get("forslagstype", []))
        rule_market = derived.get("marked", "alle")
        if policy_types and not rule_types.intersection(policy_types):
            continue
        if not _market_matches(rule_market, market):
            continue

        section = sections.get(str(rule.get("underseksjon")), {})
        searchable = " ".join(
            [
                rule.get("tekst", ""),
                section.get("tittel", ""),
            ]
        )
        rule_terms = set(_matched_terms(searchable))
        matched_terms = sorted(set(text_terms).intersection(rule_terms))
        if not matched_terms:
            continue
        score = 2 * len(matched_terms) + (1 if rule_market == "alle" else 0)

        scored.append(
            (
                score,
                {
                    "rule_id": rule["id"],
                    "policy_area": section.get("tittel", ""),
                    "policy_text": rule["tekst"],
                    "page": rule.get("side"),
                    "direction_if_conditions_met": derived.get("handling"),
                    "scope": _market_label(rule_market),
                    "requires_judgement": bool(derived.get("skjonn", False)),
                    "matched_keywords": matched_terms,
                },
            )
        )

    scored.sort(key=lambda item: (-item[0], item[1]["rule_id"]))
    candidates = [candidate for _, candidate in scored[:top_k]]
    actions = {
        candidate["direction_if_conditions_met"]
        for candidate in candidates
        if candidate["direction_if_conditions_met"] in {"FOR", "MOT"}
    }
    no_guideline_match = not candidates
    conflicting_actions = len(actions) > 1
    judgement_needed = any(
        candidate["requires_judgement"] for candidate in candidates
    )
    review_reasons = [
        reason
        for reason, condition in (
            (
                "no relevant guideline found; broader search or human review needed",
                no_guideline_match,
            ),
            ("candidate rules require additional judgement", judgement_needed),
            ("candidate rules contain conflicting directions", conflicting_actions),
        )
        if condition
    ]
    return {
        "proposal": {
            "proposal_type": proposal_type,
            "proposal_text": proposal_text,
            "market": market,
            "company": company,
            "country": country,
        },
        "candidate_rules": candidates,
        "needs_human_review": bool(review_reasons),
        "review_reasons": review_reasons,
    }


def analyze_proposal(
    proposal: dict[str, str],
    guidelines: dict[str, Any],
    *,
    top_k: int = 5,
) -> dict[str, Any]:
    """Retrieve policy candidates for one proposal."""
    return find_candidate_rules(
        proposal.get("proposal_type", ""),
        proposal.get("proposal_text", ""),
        proposal.get("market"),
        guidelines,
        company=proposal.get("company", ""),
        country=proposal.get("country", ""),
        top_k=top_k,
    )


def analyze_input_row(
    row: dict[str, str],
    guidelines: dict[str, Any],
    top_k: int = 5,
) -> dict[str, Any]:
    """Analyze one prepared input row and preserve its stable proposal key."""
    required = ("meeting_id", "item_no", "proposal_type", "proposal_text", "market")
    missing = [field for field in required if field not in row]
    if missing:
        raise ValueError(f"Input row is missing required fields: {', '.join(missing)}")
    result = analyze_proposal(row, guidelines, top_k=top_k)
    result["proposal_key"] = {
        "meeting_id": row["meeting_id"],
        "item_no": row["item_no"],
    }
    return result


def analyze_input_file(
    path: str | Path,
    guidelines: dict[str, Any],
    top_k: int = 5,
    limit: int | None = None,
    proposal_type: str | None = None,
    one_per_type: bool = False,
) -> list[dict[str, Any]]:
    """Analyze prepared inputs without reading evaluation labels."""
    with Path(path).open(encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        required = {"meeting_id", "item_no", "proposal_type", "proposal_text", "market"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(
                f"Input CSV is missing required columns: {', '.join(sorted(missing))}"
            )
        rows = []
        seen_types: set[str] = set()
        for row in reader:
            if proposal_type and row.get("proposal_type") != proposal_type:
                continue
            row_type = row.get("proposal_type", "")
            if one_per_type and row_type in seen_types:
                continue
            seen_types.add(row_type)
            rows.append(analyze_input_row(row, guidelines, top_k=top_k))
            if limit is not None and len(rows) >= limit:
                break
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--guidelines", default=str(DEFAULT_GUIDELINES))
    parser.add_argument("--input", type=Path, help="Prepared inputs.csv to process.")
    parser.add_argument("--output", type=Path, help="Write batch results as JSONL.")
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Write batch results as indented JSON instead of JSONL.",
    )
    parser.add_argument("--limit", type=int, help="Limit batch rows for a smoke test.")
    parser.add_argument(
        "--filter-type",
        help="In batch mode, only process this proposal type.",
    )
    parser.add_argument(
        "--one-per-type",
        action="store_true",
        help="In batch mode, process the first row for each proposal type.",
    )
    parser.add_argument("--proposal-type")
    parser.add_argument("--proposal-text")
    parser.add_argument("--market")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    if args.input and args.proposal_text:
        parser.error("--input cannot be combined with single-proposal arguments.")
    if not args.input and not (args.proposal_type and args.proposal_text):
        parser.error("Provide --input or both --proposal-type and --proposal-text.")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive.")

    guidelines = load_guidelines(args.guidelines)
    if args.input:
        results = analyze_input_file(
            args.input,
            guidelines,
            top_k=args.top_k,
            limit=args.limit,
            proposal_type=args.filter_type,
            one_per_type=args.one_per_type,
        )
        if args.pretty:
            output = json.dumps(results, ensure_ascii=False, indent=2)
        else:
            output = "\n".join(
                json.dumps(result, ensure_ascii=False) for result in results
            )
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(output + ("\n" if output else ""), encoding="utf-8")
        else:
            print(output)
        return

    proposal = {
        "proposal_type": args.proposal_type,
        "proposal_text": args.proposal_text,
        "market": args.market or "",
    }
    result = analyze_proposal(proposal, guidelines, top_k=args.top_k)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
