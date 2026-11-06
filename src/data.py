"""Data locations, decision records, and saved assessment storage."""

import json
from collections.abc import Callable
from dataclasses import dataclass, fields
from pathlib import Path

ROOT = str(Path(__file__).resolve().parents[1])

BOARD_FACTS = str(Path(ROOT) / "data/evidence/assessments/board_facts.jsonl")

RULE_ASSESSMENTS = str(Path(ROOT) / "data/evidence/assessments/decisions.jsonl")


JUDGE = str(Path(ROOT) / "data/evidence/assessments/judge.jsonl")


DIRECTOR_ISSUER_LINK = str(Path(ROOT) / "data/evidence/director_issuer_link.csv")

DIRECTOR_ROLES = str(Path(ROOT) / "data/evidence/director_roles.csv")

COMPANY_FACTS = str(Path(ROOT) / "data/evidence/jev_pipeline/company_facts.csv")

COMPONENTS_2026 = str(Path(ROOT) / "data/evidence/jev_pipeline/components_2026.csv")

COMPONENTS = str(Path(ROOT) / "data/evidence/jev_pipeline/components_{year}.csv")

DOCUMENTS = str(Path(ROOT) / "data/evidence/jev_pipeline/documents_2026.csv")


PROXY_EXCERPTS = str(Path(ROOT) / "data/evidence/proxy_excerpts")


OUTPUTS = str(Path(ROOT) / "data/outputs")

GUIDELINES = str(Path(ROOT) / "data/policy/guidelines_2025.json")

LIVE_GUIDELINES = str(Path(ROOT) / "data/policy/guidelines_live.json")

POSITION_PAPERS = str(Path(ROOT) / "data/policy/position_papers.json")


VOTES = str(Path(ROOT) / "data/raw/real_votes.csv")

ENV = str(Path(ROOT) / ".env")


@dataclass
class Decision:
    dataset: str
    key: str
    meeting_date: str
    company: str
    proposal: str
    board_recommendation: str
    suggested_vote: str
    probability_against_board: str
    band: str
    decided_by: str
    review_reason: str
    model: str
    reasons: str
    guideline: str
    guideline_text: str
    evidence_url: str
    actual_against_board: int
    actual_vote: str


COLUMNS = [f.name for f in fields(Decision)]


def read_records(path: str, key: Callable) -> dict:
    records = {}
    if Path(path).exists():
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                record = json.loads(line)
                records[key(record)] = record
    return records
