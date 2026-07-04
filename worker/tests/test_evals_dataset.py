"""Tests for the eval dataset and promotion gate (worker/evals/dataset.py)."""
import unittest

from worker import config
from worker.evals import dataset
from worker.evals.schema import JudgeScores


class QuestionSetTests(unittest.TestCase):
    def test_every_question_is_well_formed(self):
        for q in dataset.QUESTIONS:
            self.assertTrue(q["id"])
            self.assertTrue(q["question"].strip())
            self.assertIn("depth", q)

    def test_ids_are_unique(self):
        ids = [q["id"] for q in dataset.QUESTIONS]
        self.assertEqual(len(ids), len(set(ids)))

    def test_depths_are_known_profiles(self):
        for q in dataset.QUESTIONS:
            self.assertIn(q["depth"], config.DEPTH_PROFILES)


class ThresholdTests(unittest.TestCase):
    def test_thresholds_cover_every_judged_metric(self):
        judged_metrics = set(JudgeScores.model_fields) - {"reasoning"}
        self.assertEqual(set(dataset.THRESHOLDS), judged_metrics)

    def test_thresholds_are_fractions(self):
        for value in dataset.THRESHOLDS.values():
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)

    def test_minimise_set_is_a_subset_of_the_thresholds(self):
        self.assertTrue(dataset.MINIMISE.issubset(dataset.THRESHOLDS))
        self.assertIn("hallucination_rate", dataset.MINIMISE)


if __name__ == "__main__":
    unittest.main()
