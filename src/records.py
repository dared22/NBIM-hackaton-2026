"""Label-free records shared by retrieval and downstream decision code."""

from copy import deepcopy
from datetime import date
from typing import TypedDict

INPUT_COLUMNS = (
    "meeting_id",
    "item_no",
    "company_id",
    "company",
    "ticker",
    "country",
    "market",
    "meeting_date",
    "proposal_number",
    "proposal_text",
    "proposal_type",
    "proponent",
    "mgmt_rec",
)


class ProposalInput(TypedDict):
    meeting_id: str
    item_no: str
    company_id: str
    company: str
    ticker: str
    country: str
    market: str
    meeting_date: str
    proposal_number: str
    proposal_text: str
    proposal_type: str
    proponent: str
    mgmt_rec: str


class Fact(TypedDict):
    status: str
    value: bool | int | str | None
    sources: list[dict]
    reason: str
    scope: str


class CompanyEvidence(TypedDict):
    status: str
    meeting_id: str
    documents: list[dict]
    shared: dict[str, Fact]
    nominees: dict[str, dict]
    provenance: dict


class PolicyEvidence(TypedDict):
    version: str
    sections: list[dict]
    principles: list[dict]
    coverage: list[dict]


class EvidencePacket(TypedDict):
    schema_version: str
    proposal: ProposalInput
    company_evidence: dict
    policy: PolicyEvidence
    limitations: list[str]


def proposal_input(row: dict) -> ProposalInput:
    """Copy only approved input fields; never serialize the original row."""
    missing = set(INPUT_COLUMNS) - row.keys()
    if missing:
        raise ValueError(f"Missing input columns: {sorted(missing)}")
    result = {key: str(row[key] or "").strip() for key in INPUT_COLUMNS}
    if not all(
        result[k]
        for k in ("meeting_id", "item_no", "company_id", "company", "proposal_text")
    ):
        raise ValueError("Missing proposal identity or text")
    date.fromisoformat(result["meeting_date"])
    return result


def unknown(reason: str) -> Fact:
    """Represent a gap without manufacturing a negative fact."""
    return dict(status="unknown", value=None, sources=[], reason=reason, scope="")


def build_decision_context(packet: EvidencePacket) -> dict:
    """Provide Jev context, without granting permission for automatic voting."""
    proposal = proposal_input(packet["proposal"])
    return deepcopy(
        {
            "proposal": proposal,
            "policy_version": packet["policy"]["version"],
            "candidate_guidelines": [
                rule for s in packet["policy"]["sections"] for rule in s["rules"]
            ],
            "policy_context": {
                "principles": packet["policy"]["principles"],
                "sections": [
                    {k: s[k] for k in ("id", "title", "intro")}
                    for s in packet["policy"]["sections"]
                ],
            },
            "company_evidence": packet["company_evidence"],
            "policy_coverage": packet["policy"]["coverage"],
            "limitations": packet["limitations"],
            "routing_contract": {
                "automatic_for_allowed": False,
                "automatic_mot_requires": [
                    "selected fully sourced rule condition",
                    "no material conflicts or unresolved exceptions",
                    "decision probability gate passed",
                ],
                "otherwise": "human_review",
            },
        }
    )
