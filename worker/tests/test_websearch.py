"""Tests for the Tavily-backed web_search tool (worker/agent/websearch.py)."""
import sys
import types
import unittest
from unittest import mock

from worker.agent.websearch import make_web_search


class _FakeTavilyClient:
    """Stands in for tavily.TavilyClient; records the query and returns canned hits."""

    last_kwargs = None

    def __init__(self, api_key):
        self.api_key = api_key

    def search(self, **kwargs):
        _FakeTavilyClient.last_kwargs = kwargs
        return {
            "results": [
                {"title": "T", "url": "https://a", "content": "body"},
                {"title": None, "url": None, "content": None},  # missing fields
                {},  # entirely empty
            ]
        }


def _install_fake_tavily():
    module = types.ModuleType("tavily")
    module.TavilyClient = _FakeTavilyClient
    return mock.patch.dict(sys.modules, {"tavily": module})


class MakeWebSearchTests(unittest.TestCase):
    def test_returns_none_without_an_api_key(self):
        self.assertIsNone(make_web_search(""))

    def test_builds_a_callable_when_configured(self):
        with _install_fake_tavily():
            search = make_web_search("tvly_test")
        self.assertTrue(callable(search))

    def test_normalises_results_and_fills_missing_fields(self):
        with _install_fake_tavily():
            search = make_web_search("tvly_test")
            results = search("kafka vs rabbitmq", 3)
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0], {"title": "T", "url": "https://a", "content": "body"})
        # None and absent fields both normalise to empty strings.
        self.assertEqual(results[1], {"title": "", "url": "", "content": ""})
        self.assertEqual(results[2], {"title": "", "url": "", "content": ""})

    def test_passes_the_query_and_result_cap_through(self):
        with _install_fake_tavily():
            search = make_web_search("tvly_test")
            search("some query", 5)
        self.assertEqual(_FakeTavilyClient.last_kwargs["query"], "some query")
        self.assertEqual(_FakeTavilyClient.last_kwargs["max_results"], 5)


if __name__ == "__main__":
    unittest.main()
