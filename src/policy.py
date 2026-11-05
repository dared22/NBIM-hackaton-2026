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
    """Assess only the facts needed by a logical branch, never an overall vote."""
    required = REQUIREMENTS.get(rule_id)
    values = {key: f["value"] for key, f in facts.items() if f["status"] == "known"}

    def result(keys: tuple | list, concern: bool | None = None, **extra) -> dict:
        missing = [k for k in keys if k not in values]
        status = "incomplete" if missing else "ready"
        if any(facts.get(k, {}).get("status") == "conflicting" for k in keys):
            status = "conflicting"
        return (
            dict(
                status=status,
                required_fact_ids=list(keys),
                missing_fact_ids=missing,
                supporting_fact_ids=[k for k in keys if k in values],
                concern=concern,
                reason=(
                    "conflicting_required_facts"
                    if status == "conflicting"
                    else "missing_required_facts" if missing else ""
                ),
            )
            | extra
        )

    if required is None:
        return result([], status="not_implemented")

    # A false prerequisite settles a conjunction even if another fact conflicts.
    exclusions = {
        "1.1.1": {
            "company_size": ("small",),
            "independent": (True,),
            "executive": (True,),
        },
        "1.1.2": {
            "company_size": ("small",),
            "independent": (True,),
            "executive": (True,),
        },
        "1.1.3": {"company_size": ("large", "mid"), "nomination_chair": (False,)},
        "1.2.1": {"executive": (False,), "remuneration_member": (False,)},
        "1.2.2": {"executive": (False,), "audit_member": (False,)},
        "1.2.3": {"independent": (True,)},
        "1.3.1": {"board_chair": (False,), "ceo": (False,)},
    }
    for key, excluded_values in exclusions.get(rule_id, {}).items():
        if key in values and values[key] in excluded_values:
            return result([key], False)

    if rule_id in {"1.1.1", "1.1.2"}:
        if "majority_control" in values and values["majority_control"] != (
            rule_id == "1.1.2"
        ):
            return result(["majority_control"], False, status="not_applicable")
        if all(k in values for k in required):
            multiplier = 3 if rule_id == "1.1.2" else 2
            return result(
                required,
                values["board_independent"] * multiplier < values["board_total"],
            )
    elif rule_id == "1.1.3":
        if all(k in values for k in required):
            return result(required, values["board_independent"] < 2)
    elif rule_id in {"1.2.1", "1.2.2"}:
        if all(k in values for k in required):
            return result(required, True)
    elif rule_id == "1.2.3":
        if all(k in values for k in required):
            return result(
                required, 2 * values["audit_independent"] < values["audit_total"]
            )
    elif rule_id == "1.3.1":
        if values.get("board_chair") is True and values.get("ceo") is True:
            if values.get("founder") is False:
                return result(required, True)
            assessment = result(
                required, True, reason="founder_exception_requires_review"
            )
            if assessment["status"] != "conflicting":
                assessment["status"] = "incomplete"
            return assessment
    elif rule_id == "2.1.1":
        for key, threshold in (("board_count_min", 5), ("chair_count_min", 2)):
            if values.get(key, 0) > threshold:
                return result([key], True)
        assessment = result(
            required, reason="incomplete_roles_or_discretionary_workload"
        )
        if assessment["status"] != "conflicting":
            assessment["status"] = "incomplete"
        return assessment
    return result(required)


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
                        "supporting_fact_ids",
                        "missing_fact_ids",
                        "concern",
                        "reason",
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
