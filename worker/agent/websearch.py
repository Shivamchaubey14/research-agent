"""Client-side web search for the research loop.

Groq's chat models have no server-side web search (unlike its compound
systems), so the agent calls a ``web_search`` tool that we back with Tavily —
a search API built for LLM agents that returns clean, snippet-sized results.

Web search is optional: if no ``TAVILY_API_KEY`` is configured the factory
returns ``None`` and the loop simply runs without the tool (document search
only, or no search at all).
"""
from typing import Callable, Optional

# (query, max_results) -> list of {"title", "url", "content"} dicts.
WebSearch = Callable[[str, int], list]


def make_web_search(api_key: str) -> Optional[WebSearch]:
    """Build a Tavily-backed search function, or ``None`` if unconfigured."""
    if not api_key:
        return None

    # Imported lazily so the dependency is only needed when web search is on.
    from tavily import TavilyClient

    client = TavilyClient(api_key=api_key)

    def search(query: str, max_results: int) -> list:
        response = client.search(
            query=query,
            max_results=max_results,
            search_depth="advanced",
        )
        results = []
        for item in response.get("results", []):
            results.append(
                {
                    "title": item.get("title", "") or "",
                    "url": item.get("url", "") or "",
                    "content": item.get("content", "") or "",
                }
            )
        return results

    return search
