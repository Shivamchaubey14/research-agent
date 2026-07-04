"""Tests for the versioned agent prompts (worker/agent/prompts.py)."""
import unittest

from worker.agent import prompts


class SystemPromptTests(unittest.TestCase):
    def test_stage_prompts_are_non_empty(self):
        for text in (prompts.PLANNER_SYSTEM, prompts.RESEARCHER_SYSTEM, prompts.SYNTHESIZER_SYSTEM):
            self.assertIsInstance(text, str)
            self.assertTrue(text.strip())

    def test_synthesizer_states_the_grounding_contract(self):
        # The synthesis stage must instruct citing every material claim.
        self.assertIn("citation", prompts.SYNTHESIZER_SYSTEM.lower())


class UserPromptTests(unittest.TestCase):
    def test_plan_prompt_embeds_the_question(self):
        self.assertIn("What is RAG?", prompts.plan_user_prompt("What is RAG?"))

    def test_research_prompt_numbers_the_sub_questions(self):
        text = prompts.research_user_prompt("Q", ["first", "second", "third"])
        self.assertIn("Q", text)
        self.assertIn("1. first", text)
        self.assertIn("2. second", text)
        self.assertIn("3. third", text)

    def test_research_prompt_handles_an_empty_plan(self):
        text = prompts.research_user_prompt("Q", [])
        self.assertIn("Q", text)

    def test_synthesis_prompt_embeds_the_question(self):
        self.assertIn("Compare X and Y", prompts.synthesis_user_prompt("Compare X and Y"))


if __name__ == "__main__":
    unittest.main()
