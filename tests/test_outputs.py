"""Regression checks for prediction exports."""

import csv
import hashlib
import json
import unittest

from tests.support import get_outputs


class DashboardExportTests(unittest.TestCase):
    """Main's decisions in the column layout of the team's demo."""

    @classmethod
    def setUpClass(cls):

        from src import outputs as ex

        cls.ex = ex
        with open(
            get_outputs() / "dashboard/predictions_main.csv", encoding="utf-8", newline=""
        ) as f:
            cls.rows = list(csv.DictReader(f))
        with open(get_outputs() / "decisions_2026.csv", encoding="utf-8", newline="") as f:
            cls.decisions = {
                d["key"]: d for d in csv.DictReader(f) if d["dataset"].startswith("NBIM votes")
            }

    def test_every_decision_is_there_with_the_same_vote_and_route(self):
        self.assertEqual(len(self.rows), len(self.decisions))
        for r in self.rows:
            d = self.decisions[f"{r['meeting_id']}-{r['item_no']}"]
            self.assertEqual(r["vote"], d["suggested_vote"])
            self.assertEqual(r["route"] == "human_review", d["decided_by"] == "human review")
            self.assertEqual(r["route"] == "human_review", bool(r["review_reason"]))

    def test_the_fields_have_the_form_the_demo_reads(self):
        import json

        codes = {
            "review_band",
            "rule_needs_person",
            "instruction_in_text",
            "no_citation",
            "low_confidence",
        }
        for r in self.rows:
            self.assertEqual(list(r), self.ex.COLUMNS)
            self.assertTrue(set(r["review_reason"].split(";")) <= codes | {""}, r["review_reason"])
            self.assertTrue(0 <= float(r["confidence"]) <= 1 and 0 <= float(r["p_combined"]) <= 1)
            self.assertIsInstance(json.loads(r["documents"]), list)
            self.assertIsInstance(json.loads(r["passages"]), dict)
            self.assertIn(r["vote"], ("FOR", "MOT", "AVSTÅ", ""))

    def test_the_document_links_hold_no_answer(self):
        with open(self.ex.DOCUMENTS, encoding="utf-8") as f:
            text = f.read().lower()
        self.assertEqual(
            text.split("\n")[0], "meeting_id,item_no,document_url,document_label,documents"
        )
        for word in ("nbim_vote", "against_board", "rationale", "voted"):
            self.assertNotIn(word, text)
        self.assertGreater(sum(1 for r in self.rows if r["document_url"]), 500)

    def test_review_reasons_are_mapped_to_the_nearest_code(self):
        self.assertEqual(
            self.ex.review_codes(
                "the model is unsure; low information: no earlier votes at this company"
            ),
            "review_band;low_confidence",
        )
        self.assertEqual(
            self.ex.review_codes("security flag: the wording does not read like a ballot item"),
            "instruction_in_text",
        )
        self.assertEqual(self.ex.review_codes(""), "")


class ReplayTests(unittest.TestCase):
    def test_unaffected_general_decisions_remain_identical(self):
        with (get_outputs() / "decisions_2026.csv").open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        affected = [
            "2086078-4",
            "2064967-5",
            "2052819-15",
            "2045311-14",
            "2064275-5",
            "2085617-10",
            "2066391-13",
            "2057632-11",
            "2056629-10",
            "2052809-12",
            "2066000-12",
            "2067587-5",
            "2063407-13",
            "2054683-13",
            "2072116-1",
            "2055590-13",
            "2059500-13",
            "2049868-15",
        ]
        self.assertEqual(len(rows), 1539)
        self.assertTrue(set(affected) <= {r["key"] for r in rows})
        self.assertFalse(any("pay model" in r["model"] for r in rows))
        unchanged = sorted([r for r in rows if r["key"] not in affected], key=lambda r: r["key"])
        self.assertEqual(len(unchanged), 1521)
        actual = hashlib.sha256(
            json.dumps(
                unchanged, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        self.assertEqual(actual, "cca4720b6f655bde8ca8ca59dd55fc7487f17f1ac3c0ff64a228cec74123ffad")
        self.assertFalse(list(get_outputs().glob("*.md")))
        self.assertFalse((get_outputs() / "dashboard/predictions_main_pay.csv").exists())


class OutputGenerationTests(unittest.TestCase):
    def test_prediction_writes_csv_and_console_tables_without_markdown_reports(self):
        import contextlib
        import io
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        from src.data import COLUMNS, Decision
        from src.outputs import write_outputs

        row = {column: "" for column in COLUMNS}
        row.update(probability_against_board="0.1", actual_against_board=0)
        decision = Decision(**row)
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            with (
                patch("src.outputs.export_dashboard") as export,
                contextlib.redirect_stdout(io.StringIO()) as terminal,
            ):
                write_outputs([decision], output)
            self.assertTrue((output / "decisions_2026.csv").is_file())
            self.assertEqual(list(output.glob("*.md")), [])
            self.assertIn("MOT vote quality", terminal.getvalue())
            self.assertIn("Review routing", terminal.getvalue())
            self.assertIn("┌", terminal.getvalue())
            self.assertNotIn("###", terminal.getvalue())
            self.assertNotIn("US executive pay", terminal.getvalue())
            self.assertTrue(terminal.getvalue().endswith(f"Wrote predictions to {output}\n"))
            export.assert_called_once_with(output)

    def test_console_metrics_count_reviewed_votes_and_freeze_baseline_history(self):
        from unittest.mock import patch

        from src.data import COLUMNS, Decision
        from src.outputs import console_tables

        def decision(key, actual, route):
            row = {column: "" for column in COLUMNS}
            row.update(
                key=key,
                actual_vote=actual,
                suggested_vote="MOT",
                board_recommendation="FOR",
                decided_by=route,
            )
            return Decision(**row)

        decisions = [
            decision("new-1", "MOT", "automatic"),
            decision("new-2", "MOT", "human review"),
            decision("new-3", "FOR", "automatic"),
        ]
        votes = [
            {
                "meeting_id": "old",
                "item_no": "1",
                "company_id": "c",
                "text_key": "one",
                "meeting_date": "2025-01-01",
                "nbim_vote": "MOT",
            }
        ]
        votes += [
            {
                "meeting_id": "new",
                "item_no": str(i),
                "company_id": "c",
                "text_key": key,
                "meeting_date": "2026-01-01",
                "nbim_vote": "FOR",
            }
            for i, key in enumerate(["one", "two", "three"], 1)
        ]
        with patch("src.models.history.read_votes", return_value=votes):
            before = console_tables(decisions)
            automatic = next(line for line in before.splitlines() if "Automatic only" in line)
            self.assertEqual(automatic.count("50.0%"), 3)
            baseline = next(line for line in before.splitlines() if "Repeat last vote" in line)
            self.assertIn("100.0%", baseline)
            self.assertIn("50.0%", baseline)
            for row in votes:
                if row["meeting_date"].startswith("2026"):
                    row["nbim_vote"] = "MOT"
            self.assertEqual(console_tables(decisions), before)
