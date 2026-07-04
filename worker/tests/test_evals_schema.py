"""Tests for the LLM judge's score schema (worker/evals/schema.py)."""
import unittest

from pydantic import ValidationError

from worker.evals.schema import JudgeScores


class JudgeScoresTests(unittest.TestCase):
    def test_parses_a_full_scorecard(self):
        scores = JudgeScores.model_validate(
            {
                "faithfulness": 0.9,
                "citation_validity": 0.85,
                "answer_relevance": 0.95,
                "hallucination_rate": 0.05,
                "reasoning": "well grounded",
            }
        )
        self.assertEqual(scores.faithfulness, 0.9)
        self.assertEqual(scores.reasoning, "well grounded")

    def test_all_metric_fields_are_required(self):
        with self.assertRaises(ValidationError):
            JudgeScores.model_validate({"faithfulness": 0.9, "reasoning": "partial"})

    def test_integer_scores_are_coerced_to_float(self):
        scores = JudgeScores(
            faithfulness=1,
            citation_validity=1,
            answer_relevance=1,
            hallucination_rate=0,
            reasoning="ok",
        )
        self.assertIsInstance(scores.faithfulness, float)
        self.assertEqual(scores.hallucination_rate, 0.0)


if __name__ == "__main__":
    unittest.main()
