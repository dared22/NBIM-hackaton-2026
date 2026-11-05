import contextlib
import copy
import io
import math
import unittest
from unittest.mock import mock_open, patch

from benchmark import model


def proposal(date, item, outcome):
    return {
        "meeting_date": date, "company_id": "company", "proposal_type": "type",
        "country": "NO", "text_key": "same proposal", "y": outcome,
        "meeting_id": date, "item_no": str(item),
    }


class ScoringTests(unittest.TestCase):
    def test_threshold_uses_exact_scores(self):
        scores, labels = [0.1004, 0.10049], [0, 1]
        threshold = model.best_f1_threshold(scores, labels)
        self.assertEqual(model.prf([p >= threshold for p in scores], labels)[2], 1.0)

    def test_average_precision_groups_tied_scores(self):
        self.assertEqual(model.average_precision([0.5, 0.5], [1, 0]), 0.5)
        self.assertEqual(model.average_precision([0.5, 0.5], [0, 1]), 0.5)
        self.assertAlmostEqual(model.average_precision([0.9, 0.8, 0.7], [1, 0, 1]), 5 / 6)

    def test_metrics_match_hand_counted_confusion_matrix(self):
        result = model.prf([True, True, False, False], [1, 0, 1, 0])
        self.assertEqual(result, (0.5, 0.5, 0.5, 1, 1, 1))

    def test_accuracy_counts_correct_predictions_in_both_classes(self):
        rows = [{"y": y} for y in [1, 0, 0, 0]]
        result = model.metric_row("Always with board", [False] * 4, rows)
        self.assertEqual(result[1:5], ["0.0%", "0.0%", "0.0%", "75.0%"])
        result = model.metric_row("Mixed predictions", [True, True, False, False], rows)
        self.assertEqual(result[1:5], ["50.0%", "100.0%", "66.7%", "75.0%"])

    def test_history_cannot_see_same_day_or_future_labels(self):
        rows = [proposal("2024-01-01", 1, 0), proposal("2024-01-01", 2, 1),
                proposal("2025-01-01", 1, 0)]
        changed = copy.deepcopy(rows)
        for row in changed:
            row["y"] = 1 - row["y"]
        model.add_history_features(rows)
        model.add_history_features(changed)
        self.assertEqual(rows[0]["x"], rows[1]["x"])
        self.assertEqual(rows[0]["x"], changed[0]["x"])
        self.assertEqual(rows[1]["x"], changed[1]["x"])
        self.assertIsNone(rows[0]["prev_same_item"])
        self.assertEqual(rows[2]["prev_same_item"], 1)
        self.assertNotEqual(rows[2]["x"], changed[2]["x"])

    def test_holdout_outcomes_cannot_change_scores_or_threshold(self):
        rows = [proposal(f"{year}-{month:02d}-01", month, (year + month) % 3 == 0)
                for year in range(2022, 2027) for month in range(1, 7)]
        changed = copy.deepcopy(rows)
        for row in changed:
            if row["meeting_date"].startswith("2026"):
                row["y"] = 1 - row["y"]
        model.add_history_features(rows)
        model.add_history_features(changed)
        _, original, weights, threshold = model.run_year(rows, 2026)
        _, rescored, new_weights, new_threshold = model.run_year(changed, 2026)
        self.assertEqual(weights, new_weights)
        self.assertEqual(threshold, new_threshold)
        self.assertEqual([r["p"] for r in original], [r["p"] for r in rescored])
        self.assertEqual([r["band"] for r in original], [r["band"] for r in rescored])

    def test_validation_outcomes_cannot_change_validation_scores(self):
        rows = [proposal(f"{year}-{month:02d}-01", month, (year + month) % 3 == 0)
                for year in range(2022, 2027) for month in range(1, 7)]
        changed = copy.deepcopy(rows)
        for row in changed:
            if row["meeting_date"].startswith("2025"):
                row["y"] = 1 - row["y"]
        scores = []
        for sample in (rows, changed):
            model.add_history_features(sample)
            with patch.object(model, "best_f1_threshold", wraps=model.best_f1_threshold) as select:
                model.run_year(sample, 2026)
                scores.append(select.call_args.args[0])
        self.assertEqual(scores[0], scores[1])

    def test_same_budget_report_does_not_expand_ties(self):
        rows = [{"p": 0.4, "y": i % 2, "prev_same_item": 1 if i == 0 else 0,
                 "band": "likely AGAINST board", "x": []} for i in range(4)]
        with patch.object(model, "read_votes", return_value=rows), \
                patch.object(model, "run_year", return_value=(rows, rows, [0.0], 0.3)), \
                patch.object(model, "table") as report, \
                patch("builtins.open", mock_open()), patch("sys.argv", ["model.py"]), \
                contextlib.redirect_stdout(io.StringIO()):
            for row in rows:
                row.update(dict.fromkeys(["meeting_date", "company", "country", "proposal_type",
                                          "proposal_text", "mgmt_rec"], ""))
            model.main()
        same_budget = report.call_args_list[0].args[1][2]
        headers = report.call_args_list[0].args[0]
        self.assertEqual(same_budget[headers.index("Flagged")], 1)

    def test_logistic_fit_satisfies_penalized_gradient(self):
        xs = [[-2.0], [-1.0], [0.0], [1.0], [2.0]]
        ys = [0, 0, 1, 0, 1]
        weights = model.fit_logistic(xs, ys)
        errors = [model.predict(weights, x) - y for x, y in zip(xs, ys)]
        self.assertAlmostEqual(sum(errors), 0.0, places=7)
        self.assertAlmostEqual(sum(e * x[0] for e, x in zip(errors, xs)) + weights[1], 0.0, places=7)
        self.assertTrue(all(math.isfinite(w) for w in weights))


if __name__ == "__main__":
    unittest.main()
