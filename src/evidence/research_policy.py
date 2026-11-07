"""Policy-derived candidate rules for the independent researched Jev experiment."""

import json
from pathlib import Path

from src import data as paths

ALL_SECTIONS = (
    "1.1",
    "1.2",
    "1.3",
    "2.1",
    "2.2",
    "2.3",
    "3.1",
    "3.2",
    "3.3",
    "4.1",
    "4.2",
    "4.3",
    "5.1",
    "5.2",
    "5.3",
    "6.1",
    "6.2",
    "6.2-AT",
    "6.3",
)
TYPE_SECTIONS = {
    "DIRECTOR_ELECTION": (*ALL_SECTIONS[:8], "5.1.4"),
    "AUDITOR": ("5.1",),
    "FIN_STATEMENTS": ("5.2",),
    "DISCHARGE": ("3.2.6",),
    "SAY_ON_PAY": ("3.3",),
    "DIRECTOR_PAY": ("3.3",),
    "EQUITY_PLAN": ("3.3", "6.1"),
    "SAY_ON_PAY_FREQ": (),  # No numbered rule specifies a voting frequency.
    "SHARE_ISSUANCE": ("6.1",),
    "MERGER": ("6.2", "6.3"),
    "RPT": ("6.3",),
    "ANTITAKEOVER": ("6.2-AT",),
    "CLASSIFY_BOARD": ("3.1", "6.2-AT"),
    "DUAL_CLASS": ("4.1",),
    "SHP_INDEP_CHAIR": ("1.3",),
    "SHP_GOVERNANCE": ("3.1", "4.1", "4.2", "4.3", "6.2-AT"),
    "SHP_SUSTAINABILITY": ("5.3",),
    "ARTICLES": ALL_SECTIONS,
    "ROUTINE": ("4.2",),
    "OTHER_BUSINESS": (),
    "OTHER_MGMT": ALL_SECTIONS,
    "SHP_OTHER": ALL_SECTIONS,
    "DIVIDEND": (),
    "SHARE_REPURCHASE": ("6.1",),  # Only applies to any reissuance component.
}
CROSS_CUTTING = ("5.2.2", "4.2.4")
MANIFEST = Path(paths.ROOT) / "data/policy/research_editions.json"


def policy_for(cutoff: str, manifest: Path = MANIFEST) -> dict | None:
    """Latest verified available edition; never fall back to a later edition."""
    from src.evidence.research_sources import digest

    entries = json.loads(manifest.read_text())
    eligible = [e for e in entries if e["published_on"] < cutoff]
    for edition in sorted(eligible, key=lambda e: e["published_on"], reverse=True):
        raw = (Path(paths.ROOT) / edition["path"]).read_bytes()
        if digest(raw) != edition["sha256"]:
            raise ValueError("Policy content differs from the verified edition")
        return {**edition, "policy": json.loads(raw)}
    return None


def questions_for(proposal_type: str, edition: dict | None) -> dict:
    """One explicit, source-bound condition question per candidate rule."""
    if edition is None:
        return {}
    selectors = TYPE_SECTIONS.get(proposal_type, ALL_SECTIONS) + CROSS_CUTTING
    introductions = {
        s["id"]: " ".join(s.get("innledning", [])) for s in edition["policy"]["underseksjoner"]
    }
    questions = {}
    for rule in edition["policy"]["regler"]:
        if rule["id"] not in selectors and rule["underseksjon"] not in selectors:
            continue
        questions[rule["id"]] = {
            "rule": rule["tekst"],
            "page": rule["side"],
            "judgement": rule["avledet"]["skjonn"],
            "question": (
                "Do the factual conditions of this rule apply to this exact ballot item? "
                "Check its subject, market, thresholds, time periods and exceptions. "
                "For CEO remuneration rules, fees for non-executive directors alone do not qualify. "
                "A repurchase is not a share issuance unless reissuance is also authorized. "
                "Failure to retrieve a source is unknown, not insufficient company disclosure. "
                "Section context and exceptions: "
                + introductions[rule["underseksjon"]]
                + " Rule: "
                + rule["tekst"]
            ),
        }
    return questions
