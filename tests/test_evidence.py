"""Checks for the historical date boundary and guideline coverage."""

import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import evidence


class EvidenceTest(unittest.TestCase):
    def test_selects_only_documents_available_before_meeting(self) -> None:
        rows = [
            {"form": "DEF 14A", "filingDate": "2025-04-07", "reportDate": "2025-05-16", "accessionNumber": "a"},
            {"form": "DEF 14A", "filingDate": "2024-04-01", "reportDate": "2024-05-10", "accessionNumber": "b"},
            {"form": "DEF 14A", "filingDate": "2023-04-01", "reportDate": "2023-05-10", "accessionNumber": "c"},
            {"form": "10-K", "filingDate": "2025-02-19", "reportDate": "2024-12-31", "accessionNumber": "d"},
            {"form": "10-K", "filingDate": "2026-02-19", "reportDate": "2025-12-31", "accessionNumber": "e"},
            {"form": "8-K", "filingDate": "2025-05-19", "reportDate": "2025-05-16", "accessionNumber": "f"},
        ]
        selected = evidence.select_filings(rows, "2025-05-16")
        self.assertEqual([r["accessionNumber"] for r in selected], ["a", "b", "c", "d"])

    def test_covers_all_us_director_election_rules(self) -> None:
        rules = json.loads(evidence.GUIDELINES.read_text(encoding="utf-8"))["regler"]
        expected = {r["id"] for r in rules
                    if "styrevalg" in r["avledet"]["forslagstype"]
                    and r["avledet"]["marked"] != "fremvoksende"}
        self.assertEqual(set(evidence.RULE_FACTS), expected)
        self.assertFalse({fact for needs in evidence.RULE_FACTS.values() for fact in needs} - set(evidence.FACTS))

    def test_nominee_section_comes_from_relevant_proxy_section(self) -> None:
        text = ("William J. Sandbrook is listed on the ballot. "
                "WILLIAM J. SANDBROOK Age 67 Committees: Compensation. "
                "Independent director since 2018. William J. Sandbrook has served as a director.")
        excerpt = evidence.nominee_section(text, "William J. Sandbrook")
        self.assertIn("Committees", excerpt)
        self.assertIn("Independent", excerpt)
        self.assertTrue(excerpt in text)

    def test_rejects_fact_answer_without_matching_source_quote(self) -> None:
        documents = [{"text": "William J. Sandbrook is an independent director.",
                      "url": "https://example.test/proxy", "filing_date": "2025-04-01"}]
        raw = {"facts": [
            {"fact_id": "nominee_independent", "status": "known", "answer": "Yes",
             "source_id": "D1", "quote": "William J. Sandbrook is an independent director."},
            {"fact_id": "nominee_ceo", "status": "known", "answer": "No",
             "source_id": "D1", "quote": "The nominee is not CEO."},
        ]}
        answers = evidence.checked_facts(raw, documents, "William J. Sandbrook")
        self.assertEqual(answers["nominee_independent"]["status"], "known")
        self.assertEqual(answers["nominee_independent"]["answer"],
                         "William J. Sandbrook is an independent director.")
        self.assertEqual(answers["nominee_ceo"]["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
