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

# The default Groq model. gpt-oss-120b has reliable function calling and
# supports reasoning_effort; its free-tier limit is ~8k tokens/minute, so the
# depth profiles below keep each request small enough to fit. (llama-3.3-70b has
# a higher TPM ceiling but emits malformed tool calls too often to drive the
# agent's tool loop reliably.) Override with AGENT_MODEL on a paid tier.
DEFAULT_MODEL = "openai/gpt-oss-120b"

# Groq's chat models have no server-side web search (only its "compound"
# systems do), so the agent runs its own client-side web_search tool
# (Tavily-backed, see worker/agent/websearch.py) alongside document_search.
WEB_SEARCH_TOOL_NAME = "web_search"

# Keep each web result small so the running conversation stays well under the
# free-tier per-minute token limit (a single oversize request is rejected
# outright, and waiting can't shrink it). Raise on a paid tier for richer context.
WEB_SEARCH_MAX_RESULTS = 3  # results fed back per web search
WEB_RESULT_CHAR_LIMIT = 600  # chars kept from each result's snippet

# The depth profiles use a five-level effort scale; Groq's reasoning_effort
# parameter only accepts low|medium|high, so collapse the top two levels.
EFFORT_MAP = {
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "high",
    "max": "high",
}


def supports_reasoning_effort(model: str) -> bool:
    """Whether ``model`` accepts Groq's ``reasoning_effort`` parameter.

    Only Groq's reasoning families (gpt-oss, qwen3, deepseek) take it; passing
    it to e.g. llama-3.3 is rejected, so callers gate on this.
    """
    m = model.lower()
    return any(tag in m for tag in ("gpt-oss", "qwen3", "deepseek"))

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

# Per-million-token prices (USD) used for cost accounting (FR-RUN-6). These are
# Groq's published list prices; keep them in sync with https://groq.com/pricing.
# (On the free tier the real cost is $0, but the accounting still reports what a
# run would cost at list price.)
MODEL_PRICING = {
    "openai/gpt-oss-120b": {"input": 0.15, "output": 0.75},
    "openai/gpt-oss-20b": {"input": 0.10, "output": 0.50},
    "llama-3.3-70b-versatile": {"input": 0.59, "output": 0.79},
    "llama-3.1-8b-instant": {"input": 0.05, "output": 0.08},
    "moonshotai/kimi-k2-instruct": {"input": 1.00, "output": 3.00},
}


@dataclass(frozen=True)
class DepthProfile:
    """Resource envelope for a single research depth (FR-RUN-2)."""

    effort: str  # reasoning effort: low | medium | high | xhigh | max
    max_search_uses: int  # cap on web_search invocations per run
    max_research_turns: int  # agentic turns before the hard ceiling (FR-AGT-3)
    max_research_tokens: int  # max_tokens for each research turn
    max_synthesis_tokens: int  # max_tokens for the structured synthesis call
    token_budget: int  # soft per-run token ceiling (FR-AGT-4)
    wall_clock_seconds: int  # soft per-run wall-clock ceiling (FR-AGT-4)


# NOTE: the per-request token ceilings are kept modest because Groq's free tier
# is capped at a few thousand tokens per minute (per model); a single request
# whose prompt + max_tokens exceeds that limit is rejected outright. The LLM
# wrapper additionally backs off and retries when the per-minute limit is hit,
# so multi-step runs still complete (just more slowly). Raise these on a paid
# Groq tier for longer, richer reports.
DEPTH_PROFILES = {
    "quick": DepthProfile(
        effort="low",
        max_search_uses=3,
        max_research_turns=2,
        max_research_tokens=2000,
        max_synthesis_tokens=2000,
        token_budget=30_000,
        wall_clock_seconds=180,
    ),
    "standard": DepthProfile(
        effort="high",
        max_search_uses=4,
        max_research_turns=3,
        max_research_tokens=2500,
        max_synthesis_tokens=2500,
        token_budget=80_000,
        wall_clock_seconds=360,
    ),
    "deep": DepthProfile(
        effort="xhigh",
        max_search_uses=6,
        max_research_turns=4,
        max_research_tokens=2500,
        max_synthesis_tokens=2500,
        token_budget=150_000,
        wall_clock_seconds=600,
    ),
}

DEFAULT_DEPTH = "standard"


@dataclass(frozen=True)
class Settings:
    """Process-level configuration, resolved from the environment."""

    groq_api_key: str
    tavily_api_key: str = ""  # optional; enables the web_search tool when set
    model: str = DEFAULT_MODEL
    plan_effort: str = "medium"  # planning is cheaper than research/synthesis

    @classmethod
    def from_env(cls) -> "Settings":
        api_key = os.environ.get("GROQ_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set; the agent worker needs it to reach "
                "the Groq API."
            )
        return cls(
            groq_api_key=api_key,
            tavily_api_key=os.environ.get("TAVILY_API_KEY", ""),
            model=os.environ.get("AGENT_MODEL", DEFAULT_MODEL),
        )


def profile_for(depth: str) -> DepthProfile:
    """Return the :class:`DepthProfile` for ``depth``, defaulting to standard."""
    return DEPTH_PROFILES.get(depth, DEPTH_PROFILES[DEFAULT_DEPTH])
