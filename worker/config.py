"""Worker configuration and per-run depth profiles.

The agent's policy and budgets are versioned so behaviour is reproducible
(FR-AGT-9). ``DEPTH_PROFILES`` maps the run's depth (FR-RUN-2) onto the
iteration, search and budget ceilings the loop enforces (FR-AGT-3, FR-AGT-4).
"""
import os
from dataclasses import dataclass

# Bumped whenever the system policy, tool schema or depth profiles change so a
# run can be tied to the exact behaviour that produced it (FR-AGT-9).
AGENT_POLICY_VERSION = "2026.06.1"

# Anthropic web-search server tool (dynamic filtering; Opus 4.8 / Sonnet 4.6).
WEB_SEARCH_TOOL_TYPE = "web_search_20260209"
WEB_SEARCH_TOOL_NAME = "web_search"

# RAG ingestion (FR-RAG-2). Embeddings run locally via fastembed (no API key);
# one shared Qdrant collection holds every user's chunks, scoped at query time
# by a user_id payload filter (FR-RAG-3, FR-AUTH-5).
QDRANT_COLLECTION = "documents"
EMBED_MODEL = "BAAI/bge-small-en-v1.5"  # 384-dim, small + fast
CHUNK_SIZE = 900  # characters per chunk
CHUNK_OVERLAP = 150  # overlap between consecutive chunks

# Agent-side document retrieval (FR-RAG-3).
DOCUMENT_SEARCH_TOOL_NAME = "document_search"
RAG_TOP_K = 5  # chunks returned per document search

# Per-million-token prices (USD) used for cost accounting (FR-RUN-6).
# Cache writes bill at 1.25x input, cache reads at 0.1x input.
MODEL_PRICING = {
    "claude-opus-4-8": {"input": 5.0, "output": 25.0},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5": {"input": 1.0, "output": 5.0},
}


@dataclass(frozen=True)
class DepthProfile:
    """Resource envelope for a single research depth (FR-RUN-2)."""

    effort: str  # output_config effort: low | medium | high | xhigh | max
    max_search_uses: int  # cap on web_search invocations per research turn
    max_research_turns: int  # agentic turns before the hard ceiling (FR-AGT-3)
    max_research_tokens: int  # max_tokens for each streamed research turn
    max_synthesis_tokens: int  # max_tokens for the structured synthesis call
    token_budget: int  # soft per-run token ceiling (FR-AGT-4)
    wall_clock_seconds: int  # soft per-run wall-clock ceiling (FR-AGT-4)


DEPTH_PROFILES = {
    "quick": DepthProfile(
        effort="low",
        max_search_uses=3,
        max_research_turns=2,
        max_research_tokens=8000,
        max_synthesis_tokens=8000,
        token_budget=80_000,
        wall_clock_seconds=120,
    ),
    "standard": DepthProfile(
        effort="high",
        max_search_uses=6,
        max_research_turns=4,
        max_research_tokens=16000,
        max_synthesis_tokens=12000,
        token_budget=200_000,
        wall_clock_seconds=300,
    ),
    "deep": DepthProfile(
        effort="xhigh",
        max_search_uses=12,
        max_research_turns=6,
        max_research_tokens=16000,
        max_synthesis_tokens=16000,
        token_budget=500_000,
        wall_clock_seconds=600,
    ),
}

DEFAULT_DEPTH = "standard"


@dataclass(frozen=True)
class Settings:
    """Process-level configuration, resolved from the environment."""

    anthropic_api_key: str
    model: str = "claude-opus-4-8"
    plan_effort: str = "medium"  # planning is cheaper than research/synthesis

    @classmethod
    def from_env(cls) -> "Settings":
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set; the agent worker needs it to "
                "reach the Claude API."
            )
        return cls(
            anthropic_api_key=api_key,
            model=os.environ.get("AGENT_MODEL", "claude-opus-4-8"),
        )


def profile_for(depth: str) -> DepthProfile:
    """Return the :class:`DepthProfile` for ``depth``, defaulting to standard."""
    return DEPTH_PROFILES.get(depth, DEPTH_PROFILES[DEFAULT_DEPTH])
