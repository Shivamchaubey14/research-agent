"""Tests for token/cost accounting and rate-limit parsing (worker/agent/llm.py)."""
import unittest
from types import SimpleNamespace

from worker import config
from worker.agent.llm import Usage, _retry_after_seconds


class UsageTests(unittest.TestCase):
    def test_total_tokens_sums_input_and_output(self):
        usage = Usage(input_tokens=100, output_tokens=25)
        self.assertEqual(usage.total_tokens, 125)

    def test_add_accumulates_a_response_usage_block(self):
        usage = Usage()
        usage.add(SimpleNamespace(prompt_tokens=10, completion_tokens=4))
        usage.add(SimpleNamespace(prompt_tokens=5, completion_tokens=1))
        self.assertEqual(usage.input_tokens, 15)
        self.assertEqual(usage.output_tokens, 5)

    def test_add_tolerates_none_and_missing_fields(self):
        usage = Usage()
        usage.add(None)
        usage.add(SimpleNamespace())  # no token attributes
        self.assertEqual(usage.total_tokens, 0)

    def test_cost_uses_the_models_published_pricing(self):
        usage = Usage(input_tokens=1_000_000, output_tokens=1_000_000)
        price = config.MODEL_PRICING["openai/gpt-oss-120b"]
        expected = round(price["input"] + price["output"], 6)
        self.assertEqual(usage.cost_usd("openai/gpt-oss-120b"), expected)

    def test_unknown_model_falls_back_to_the_default_price(self):
        usage = Usage(input_tokens=1_000_000, output_tokens=0)
        default = config.MODEL_PRICING[config.DEFAULT_MODEL]
        self.assertEqual(usage.cost_usd("some/unpriced-model"), round(default["input"], 6))


class _FakeResponse:
    def __init__(self, headers):
        self.headers = headers


class RetryAfterTests(unittest.TestCase):
    def _exc(self, headers=None, message=""):
        exc = Exception(message)
        exc.response = _FakeResponse(headers or {})
        return exc

    def test_prefers_the_retry_after_header(self):
        self.assertEqual(_retry_after_seconds(self._exc(headers={"retry-after": "12"})), 12.0)

    def test_parses_a_try_again_hint_from_the_message(self):
        exc = self._exc(message="Rate limit reached, try again in 3.5s please")
        # The parser adds a small cushion past the window.
        self.assertAlmostEqual(_retry_after_seconds(exc), 4.5)

    def test_falls_back_when_nothing_is_available(self):
        self.assertEqual(_retry_after_seconds(self._exc()), 20.0)

    def test_non_numeric_header_is_ignored(self):
        exc = self._exc(headers={"retry-after": "soon"})
        self.assertEqual(_retry_after_seconds(exc), 20.0)


if __name__ == "__main__":
    unittest.main()
