"""Regression checks for models."""

import copy
import math
import unittest
from unittest.mock import patch

from src.models import history as model
from src.models import scoring as logistic
from src.models import scoring as metrics


def proposal(date, item, outcome):
    return {
        "meeting_date": date,
        "company_id": "company",
        "proposal_type": "type",
        "country": "NO",
        "text_key": "same proposal",
        "y": outcome,
        "meeting_id": date,
        "item_no": str(item),
    }


class ScoringTests(unittest.TestCase):
    def test_threshold_uses_exact_scores(self):
        scores, labels = [0.1004, 0.10049], [0, 1]
        threshold = metrics.best_f1_threshold(scores, labels)
        self.assertEqual(metrics.prf([p >= threshold for p in scores], labels)[2], 1.0)

    def test_metrics_match_hand_counted_confusion_matrix(self):
        result = metrics.prf([True, True, False, False], [1, 0, 1, 0])
        self.assertEqual(result, (0.5, 0.5, 0.5, 1, 1, 1))

    def test_history_cannot_see_same_day_or_future_labels(self):
        rows = [
            proposal("2024-01-01", 1, 0),
            proposal("2024-01-01", 2, 1),
            proposal("2025-01-01", 1, 0),
        ]
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
        rows = [
            proposal(f"{year}-{month:02d}-01", month, (year + month) % 3 == 0)
            for year in range(2022, 2027)
            for month in range(1, 7)
        ]
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
        rows = [
            proposal(f"{year}-{month:02d}-01", month, (year + month) % 3 == 0)
            for year in range(2022, 2027)
            for month in range(1, 7)
        ]
        changed = copy.deepcopy(rows)
        for row in changed:
            if row["meeting_date"].startswith("2025"):
                row["y"] = 1 - row["y"]
        scores = []
        for sample in (rows, changed):
            model.add_history_features(sample)
            with patch.object(
                metrics, "best_f1_threshold", wraps=metrics.best_f1_threshold
            ) as select:
                model.run_year(sample, 2026)
                scores.append(select.call_args.args[0])
        self.assertEqual(scores[0], scores[1])

    def test_logistic_fit_satisfies_penalized_gradient(self):
        xs = [[-2.0], [-1.0], [0.0], [1.0], [2.0]]
        ys = [0, 0, 1, 0, 1]
        weights = logistic.fit_logistic(xs, ys)
        errors = [logistic.predict(weights, x) - y for x, y in zip(xs, ys)]
        self.assertAlmostEqual(sum(errors), 0.0, places=7)
        self.assertAlmostEqual(
            sum(e * x[0] for e, x in zip(errors, xs)) + weights[1], 0.0, places=7
        )
        self.assertTrue(all(math.isfinite(w) for w in weights))
