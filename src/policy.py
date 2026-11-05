"""Exact 2025 policy lookup and reproducible evidence-informed section ranking."""

import json
from pathlib import Path

from records import CompanyEvidence, PolicyEvidence, ProposalInput

GUIDELINES = (
    Path(__file__).resolve().parents[1]
    / "startpakke/case1_stemmegivning/retningslinjer_2025.json"
)
PDF_URL = "https://www.nbim.no/contentassets/01a7ee19b5d84a73a67a365e76a0fb01/global-voting-guildeines_2025.pdf"
REQUIREMENTS = {
    "1.1.1": (
        "company_size",
        "majority_control",
        "board_independent",
        "board_total",
        "independent",
        "executive",
    ),
    "1.1.2": (
        "company_size",
        "majority_control",
        "board_independent",
        "board_total",
        "independent",
        "executive",
    ),
    "1.1.3": ("company_size", "board_independent", "nomination_chair"),
    "1.2.1": ("executive", "remuneration_member"),
    "1.2.2": ("executive", "audit_member"),
    "1.2.3": ("independent", "audit_independent", "audit_total"),
    "1.3.1": ("board_chair", "ceo", "founder"),
    "2.1.1": ("board_count_min", "chair_count_min"),
}


def supported(proposal: ProposalInput) -> bool:
    return (
        proposal["country"] == "United States"
        and proposal["market"] == "DM"
        and proposal["proposal_type"] == "DIRECTOR_ELECTION"
        and proposal["meeting_date"][:4] in {"2025", "2026"}
    )


def assess(rule_id: str, facts: dict) -> dict:
    """Evaluate only core concern signals; this is not a voting decision."""
    required_fact_ids = REQUIREMENTS.get(rule_id)
    if required_fact_ids is None:
        return dict(
            status="not_implemented",
            required_fact_ids=[],
            missing_fact_ids=[],
            concern=None,
        )
    known_values = {
        key: f["value"] for key, f in facts.items() if f["status"] == "known"
    }
    missing_fact_ids = [k for k in required_fact_ids if k not in known_values]
    result = dict(
        status="incomplete" if missing_fact_ids else "ready",
        required_fact_ids=list(required_fact_ids),
        missing_fact_ids=missing_fact_ids,
        concern=None,
    )
    if any(facts.get(k, {}).get("status") == "conflicting" for k in required_fact_ids):
        return {**result, "status": "conflicting"}

    # Known false prerequisites can rule out a condition without requiring its other facts.
    def resolved(condition: bool) -> dict:
        return {
            **result,
            "status": "ready",
            "missing_fact_ids": [],
            "concern": condition,
        }

    if rule_id in {"1.1.1", "1.1.2"}:
        if (
            known_values.get("company_size") == "small"
            or known_values.get("independent") is True
            or known_values.get("executive") is True
        ):
            return resolved(False)
        if "majority_control" in known_values and known_values["majority_control"] != (
            rule_id == "1.1.2"
        ):
            return {**resolved(False), "status": "not_applicable"}
        if not missing_fact_ids:
            threshold = 3 if rule_id == "1.1.2" else 2
            return resolved(
                known_values["board_independent"] * threshold
                < known_values["board_total"]
            )
    elif rule_id == "1.1.3":
        if (
            known_values.get("company_size") in {"large", "mid"}
            or known_values.get("nomination_chair") is False
        ):
            return resolved(False)
        if not missing_fact_ids:
            return resolved(known_values["board_independent"] < 2)
    elif rule_id in {"1.2.1", "1.2.2"}:
        if any(known_values.get(k) is False for k in required_fact_ids):
            return resolved(False)
        if not missing_fact_ids:
            return resolved(True)
    elif rule_id == "1.2.3":
        if known_values.get("independent") is True:
            return resolved(False)
        if not missing_fact_ids:
            return resolved(
                2 * known_values["audit_independent"] < known_values["audit_total"]
            )
    elif rule_id == "1.3.1":
        if known_values.get("board_chair") is False or known_values.get("ceo") is False:
            return resolved(False)
        if known_values.get("board_chair") is True and known_values.get("ceo") is True:
            if known_values.get("founder") is False:
                return resolved(True)
            return {
                **result,
                "status": "incomplete",
                "reason": "founder_exception_requires_review",
                "concern": True,
            }
    elif rule_id == "2.1.1":
        if (
            known_values.get("board_count_min", 0) > 5
            or known_values.get("chair_count_min", 0) > 2
        ):
            return resolved(True)
        # Lower bounds cannot establish an absence of overboarding, nor resolve the discretionary branch.
        return {
            **result,
            "status": "incomplete",
            "reason": "incomplete_roles_or_discretionary_workload",
        }
    return result


def select_policy(
    proposal: ProposalInput, company_evidence: CompanyEvidence
) -> PolicyEvidence:
    """Return at most three sections; preserve coverage for every candidate rule."""
    data = json.loads(GUIDELINES.read_text())
    output = dict(
        version="2025-fixed-experiment", sections=[], principles=[], coverage=[]
    )
    if not supported(proposal):
        output["reason"] = "unsupported_scope"
        return output
    nominee = company_evidence["nominees"].get(proposal["item_no"], {})
    if nominee.get("status") != "verified" or company_evidence["status"] != "verified":
        output["reason"] = nominee.get("status", company_evidence["status"])
        return output
    facts = {**company_evidence["shared"], **nominee["facts"]}
    sections = {}
    for rule in data["regler"]:
        derived = rule["avledet"]
        if (
            "styrevalg" not in derived["forslagstype"]
            or derived["marked"] == "fremvoksende"
        ):
            continue
        assessment = assess(rule["id"], facts)
        entry = dict(
            id=rule["id"],
            section_id=rule["underseksjon"],
            text=rule["tekst"],
            page=rule["side"],
            pdf_url=PDF_URL,
            **assessment,
        )
        sections.setdefault(rule["underseksjon"], []).append(entry)

    def rank(section_id: str) -> tuple:
        rules = sections[section_id]
        concerns = sum(r["concern"] is True for r in rules)
        unresolved = any(r["status"] in {"incomplete", "conflicting"} for r in rules)
        implemented = any(r["status"] != "not_implemented" for r in rules)
        tier = 3 if concerns else 2 if unresolved else 1 if implemented else 0
        return (-tier, -concerns, tuple(map(int, section_id.split("."))))

    chosen = sorted(sections, key=rank)[:3]
    for sid in chosen:
        context = next(s for s in data["underseksjoner"] if s["id"] == sid)
        output["sections"].append(
            dict(
                id=sid,
                title=context["tittel"],
                intro=context["innledning"],
                rules=sections[sid],
                selection_reason="core_concern_then_missing_then_numeric_order",
            )
        )
    for sid, rules in sections.items():
        for rule in rules:
            output["coverage"].append(
                {
                    k: rule[k]
                    for k in (
                        "id",
                        "section_id",
                        "status",
                        "required_fact_ids",
                        "missing_fact_ids",
                        "concern",
                    )
                }
                | {
                    "selected": sid in chosen,
                    "omission_reason": "" if sid in chosen else "top_three_limit",
                }
            )
    output["principles"] = [
        dict(id=p["id"], text=p["tekst"], page=p["side"], pdf_url=PDF_URL)
        for p in data["prinsipper"]
    ]
    return output
