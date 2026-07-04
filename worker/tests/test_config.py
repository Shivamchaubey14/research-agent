"""Tests for the worker's depth profiles and environment config (worker/config.py)."""
import unittest
from unittest import mock

from worker import config


class ProfileTests(unittest.TestCase):
    def test_known_depths_map_to_their_profiles(self):
        for depth in ("quick", "standard", "deep"):
            self.assertIs(config.profile_for(depth), config.DEPTH_PROFILES[depth])

    def test_unknown_depth_falls_back_to_standard(self):
        self.assertIs(config.profile_for("bogus"), config.DEPTH_PROFILES["standard"])
        self.assertIs(config.profile_for(""), config.DEPTH_PROFILES[config.DEFAULT_DEPTH])

    def test_budgets_grow_with_depth(self):
        quick = config.profile_for("quick")
        standard = config.profile_for("standard")
        deep = config.profile_for("deep")
        self.assertLess(quick.token_budget, standard.token_budget)
        self.assertLess(standard.token_budget, deep.token_budget)
        self.assertLessEqual(quick.max_search_uses, deep.max_search_uses)

    def test_profiles_are_immutable(self):
        with self.assertRaises(Exception):
            config.profile_for("quick").token_budget = 1


class ReasoningEffortTests(unittest.TestCase):
    def test_reasoning_families_are_supported(self):
        self.assertTrue(config.supports_reasoning_effort("openai/gpt-oss-120b"))
        self.assertTrue(config.supports_reasoning_effort("qwen3-32b"))
        self.assertTrue(config.supports_reasoning_effort("deepseek-r1"))

    def test_non_reasoning_models_are_not(self):
        self.assertFalse(config.supports_reasoning_effort("llama-3.3-70b-versatile"))
        self.assertFalse(config.supports_reasoning_effort("moonshotai/kimi-k2-instruct"))

    def test_effort_scale_collapses_top_levels_to_high(self):
        self.assertEqual(config.EFFORT_MAP["xhigh"], "high")
        self.assertEqual(config.EFFORT_MAP["max"], "high")
        self.assertEqual(config.EFFORT_MAP["low"], "low")


class SettingsFromEnvTests(unittest.TestCase):
    def test_missing_groq_key_raises(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(RuntimeError):
                config.Settings.from_env()

    def test_reads_keys_and_model_override(self):
        env = {
            "GROQ_API_KEY": "gsk_test",
            "TAVILY_API_KEY": "tvly_test",
            "AGENT_MODEL": "openai/gpt-oss-20b",
        }
        with mock.patch.dict("os.environ", env, clear=True):
            settings = config.Settings.from_env()
        self.assertEqual(settings.groq_api_key, "gsk_test")
        self.assertEqual(settings.tavily_api_key, "tvly_test")
        self.assertEqual(settings.model, "openai/gpt-oss-20b")

    def test_model_defaults_and_tavily_optional(self):
        with mock.patch.dict("os.environ", {"GROQ_API_KEY": "gsk_test"}, clear=True):
            settings = config.Settings.from_env()
        self.assertEqual(settings.model, config.DEFAULT_MODEL)
        self.assertEqual(settings.tavily_api_key, "")


if __name__ == "__main__":
    unittest.main()
