"""Checks for MOT metrics and historical baselines in the CLI report."""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))
import run


class PredictionReportTests(unittest.TestCase):
    def test_mot_metrics_count_false_positives_and_misses(self):
        tp, fp, fn, precision, recall, f1 = run.mot_metrics(
            [True, True, True, False], [True, False, False, True])
        self.assertEqual((tp, fp, fn), (1, 1, 2))
        self.assertAlmostEqual(precision, 0.5)
        self.assertAlmostEqual(recall, 1 / 3)
        self.assertAlmostEqual(f1, 0.4)

    def test_mot_metrics_handle_no_predictions_or_positives(self):
        self.assertEqual(run.mot_metrics([True], [False]), (0, 0, 1, 0, 0, 0))
        self.assertEqual(run.mot_metrics([False], [True]), (0, 1, 0, 0, 0, 0))
        self.assertEqual(run.mot_metrics([], []), (0, 0, 0, 0, 0, 0))

    def test_automatic_metrics_keep_reviewed_mot_votes_in_recall(self):
        rows = []
        for actual, suggested, who in [("MOT", "MOT", "automatic"), ("MOT", "MOT", "human review"),
                                       ("AVSTÅ", "MOT", "automatic")]:
            d = dict(actual_vote=actual, suggested_vote=suggested, decided_by=who, board_recommendation="FOR")
            rows.append([d.get(c, "") for c in run.COLS])
        table = run.mot_table(rows, "Sample", [])
        all_row = next(line for line in table.splitlines() if "all suggestions" in line)
        auto_row = next(line for line in table.splitlines() if "automatic only" in line)
        self.assertIn("66.7%", all_row)
        self.assertIn("100.0%", all_row)
        self.assertEqual(auto_row.count("50.0%"), 3)

    def test_baselines_use_only_prior_years_and_align_to_decision_order(self):
        votes = [dict(company_id="c", text_key="item", nbim_vote="MOT", meeting_date="2025-01-01", meeting_id="old", item_no="1"),
                 dict(company_id="c", text_key="item", nbim_vote="FOR", mgmt_rec="FOR", meeting_date="2026-01-01", meeting_id="new", item_no="1"),
                 dict(company_id="c", text_key="unseen", nbim_vote="MOT", mgmt_rec="FOR", meeting_date="2026-02-01", meeting_id="new", item_no="2")]
        pay_rows = [dict(season=2025, cusip="c", stemme="AGAINST"),
                    dict(season=2026, cusip="c", stemme="FOR", moetedato="2026-01-01", pay=30e6),
                    dict(season=2026, cusip="d", stemme="AGAINST", moetedato="2026-02-01", pay=None)]

        def decision(key):
            return [key if c == "key" else "" for c in run.COLS]

        with patch.object(run.bm, "read_votes", return_value=votes), patch.object(run.pm, "load_rows", return_value=(pay_rows, {})), \
                patch.object(run, "mot_table", return_value="table") as table:
            run.prediction_comparisons([decision("d-2026-02-01"), decision("c-2026-01-01")],
                                       [decision("new-2"), decision("new-1")])
        self.assertEqual(table.call_args_list[0].args[2], [("Baseline: repeat last vote", [False, True])])
        self.assertEqual(table.call_args_list[1].args[2], [
            ("Baseline: repeat last season", [False, True]),
            ("Baseline: CEO pay >= $25m", [False, True]),
        ])


if __name__ == "__main__":
    unittest.main()
