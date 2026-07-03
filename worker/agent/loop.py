"""The research agent loop: plan -> search -> verify -> cite (SRS §5.3).

The loop autonomously decomposes the question (FR-AGT-1), drives the Groq
tool-use interface to search the web (FR-AGT-2), iterates until the evidence is
sufficient or a hard ceiling is reached (FR-AGT-3), enforces token and
wall-clock budgets (FR-AGT-4), and synthesises a cited report whose claims are
grounded in retrieved sources (FR-AGT-5, FR-AGT-6). Every step emits a progress
event (FR-AGT-7).

Groq's chat models have no server-side search, so both web search and document
search are client-side tools: the model emits a tool call, the loop executes it
and feeds the results back as a ``tool`` message, and the model continues.
"""
import json
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from groq import APIStatusError

from worker.agent import events, prompts
from worker.agent.events import ProgressEmitter, ProgressEvent
from worker.agent.llm import LLM, Usage
from worker.agent.schema import Plan, ReportDraft
from worker.agent.websearch import make_web_search
from worker.config import (
    AGENT_POLICY_VERSION,
    DOCUMENT_SEARCH_TOOL_NAME,
    RAG_TOP_K,
    WEB_RESULT_CHAR_LIMIT,
    WEB_SEARCH_MAX_RESULTS,
    WEB_SEARCH_TOOL_NAME,
    DepthProfile,
    Settings,
    profile_for,
)


class RunCancelled(Exception):
    """Raised when a cancel was requested at a safe checkpoint (FR-RUN-5)."""


@dataclass
class AgentResult:
    """The complete output of one run, ready to persist."""

    plan: Plan
    report: ReportDraft
    usage: Usage
    cost_usd: float
    policy_version: str = AGENT_POLICY_VERSION
    sources_seen: list[dict] = field(default_factory=list)


# Callback returning True if the run should stop at the next checkpoint.
CancelCheck = Callable[[], bool]
# Callback (query, top_k) -> list of {text, doc_ref, filename, score}. Injected
# by the runner so the agent stays free of Django/Qdrant imports. None disables
# document search (web-only run).
Retriever = Callable[[str, int], list]

# Client-side tools, in Groq/OpenAI function-calling format.
_WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": WEB_SEARCH_TOOL_NAME,
        "description": (
            "Search the public web for up-to-date information. Returns a list "
            "of results, each with a title, URL and a text snippet. Use this to "
            "gather and corroborate evidence for the research question."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query."}
            },
            "required": ["query"],
        },
    },
}

_DOCUMENT_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": DOCUMENT_SEARCH_TOOL_NAME,
        "description": (
            "Search the user's uploaded documents for passages relevant to a "
            "query. Returns excerpts, each with a source reference (doc_ref). "
            "Use this to ground answers in the user's own files, alongside web "
            "search."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to look for."}
            },
            "required": ["query"],
        },
    },
}


class ResearchAgent:
    def __init__(
        self,
        settings: Settings,
        emitter: Optional[ProgressEmitter] = None,
        should_cancel: Optional[CancelCheck] = None,
        retriever: Optional[Retriever] = None,
    ):
        self._settings = settings
        self._llm = LLM(settings.groq_api_key, settings.model)
        self._emitter = emitter or events.LoggingEmitter()
        self._should_cancel = should_cancel or (lambda: False)
        self._retriever = retriever
        # Web search is optional: only wired up when a Tavily key is configured.
        self._web_search = make_web_search(settings.tavily_api_key)

    # -- public API ---------------------------------------------------------

    def run(self, question: str, depth: str = "standard") -> AgentResult:
        profile = profile_for(depth)
        started = time.monotonic()
        self._emit(events.STATUS, f"Starting research (depth={depth})",
                   policy_version=AGENT_POLICY_VERSION)

        self._checkpoint()
        plan = self._plan(question, profile)

        self._checkpoint()
        digest, sources = self._research(question, plan, profile, started)

        self._checkpoint()
        report = self._synthesize(question, digest, sources, profile)

        cost = self._llm.usage.cost_usd(self._settings.model)
        self._emit(
            events.STATUS,
            "Research complete",
            total_tokens=self._llm.usage.total_tokens,
            cost_usd=cost,
        )
        return AgentResult(
            plan=plan,
            report=report,
            usage=self._llm.usage,
            cost_usd=cost,
            sources_seen=sources,
        )

    # -- stages -------------------------------------------------------------

    def _plan(self, question: str, profile: DepthProfile) -> Plan:
        plan = self._llm.parse(
            system=prompts.PLANNER_SYSTEM,
            messages=[{"role": "user", "content": prompts.plan_user_prompt(question)}],
            schema=Plan,
            effort=self._settings.plan_effort,
            max_tokens=4000,
        )
        self._emit(
            events.PLAN,
            f"Planned {len(plan.sub_questions)} sub-questions",
            sub_questions=plan.sub_questions,
        )
        return plan

    def _research(self, question, plan, profile, started):
        """Drive the tool loop; return (evidence digest, sources).

        Offers a ``web_search`` tool when a Tavily key is configured, and a
        ``document_search`` tool when a retriever is injected. The model decides
        which to call; the loop executes each call and feeds results back until
        the model stops calling tools or a budget/turn ceiling is hit.
        """
        tools = []
        if self._web_search is not None:
            tools.append(_WEB_SEARCH_TOOL)
        if self._retriever is not None:
            tools.append(_DOCUMENT_SEARCH_TOOL)

        messages = [
            {
                "role": "user",
                "content": prompts.research_user_prompt(question, plan.sub_questions),
            }
        ]
        digest_parts: list[str] = []
        sources: list[dict] = []
        seen_urls: set[str] = set()
        seen_refs: set[str] = set()
        web_searches = 0  # enforce the per-run web-search cap (FR-AGT-3)

        for turn in range(profile.max_research_turns):
            if self._budget_exhausted(profile, started):
                self._emit(events.STATUS, "Budget reached; wrapping up research")
                break
            self._checkpoint()

            try:
                message = self._llm.chat(
                    system=prompts.RESEARCHER_SYSTEM,
                    messages=messages,
                    tools=tools,
                    effort=profile.effort,
                    max_tokens=profile.max_research_tokens,
                )
            except APIStatusError as exc:
                # A single bad turn (e.g. free-tier token limit, or the model
                # emitting a malformed tool call) shouldn't sink the whole run:
                # stop researching and synthesise from the evidence gathered so
                # far (FR-AGT-8).
                self._emit(
                    events.ERROR,
                    f"Research turn failed ({exc.status_code}); "
                    "synthesising with the evidence gathered so far",
                    error=str(exc),
                )
                break

            text = (message.content or "").strip()
            if text:
                digest_parts.append(text)
                self._emit(events.REASONING, _preview(text))

            messages.append(_assistant_message(message))

            tool_calls = message.tool_calls or []
            if not tool_calls:
                # No tool calls: the model has finished gathering evidence.
                break

            for call in tool_calls:
                result, web_searches = self._run_tool_call(
                    call, digest_parts, sources, seen_urls, seen_refs,
                    profile, web_searches,
                )
                messages.append(
                    {"role": "tool", "tool_call_id": call.id, "content": result}
                )

        return "\n\n".join(p for p in digest_parts if p.strip()), sources

    def _synthesize(self, question, digest, sources, profile) -> ReportDraft:
        self._emit(events.VERIFICATION, "Synthesising and grounding the report")
        source_lines = "\n".join(_format_source(i, s) for i, s in enumerate(sources, 1))
        evidence = (
            f"{prompts.synthesis_user_prompt(question)}\n\n"
            f"--- Evidence digest ---\n{digest or '(no evidence gathered)'}\n\n"
            f"--- Sources retrieved ---\n{source_lines or '(none)'}"
        )
        report = self._llm.parse(
            system=prompts.SYNTHESIZER_SYSTEM,
            messages=[{"role": "user", "content": evidence}],
            schema=ReportDraft,
            effort=profile.effort,
            max_tokens=profile.max_synthesis_tokens,
        )
        self._emit(
            events.REPORT,
            f"Report ready: {len(report.sections)} sections, "
            f"{len(report.citations)} citations",
            sections=len(report.sections),
            citations=len(report.citations),
        )
        return report

    # -- tool execution -----------------------------------------------------

    def _run_tool_call(
        self, call, digest_parts, sources, seen_urls, seen_refs, profile, web_searches
    ):
        """Execute one tool call; return ``(result_text, web_searches)``."""
        name = call.function.name
        try:
            args = json.loads(call.function.arguments or "{}")
        except json.JSONDecodeError:
            args = {}
        query = args.get("query", "")

        if name == WEB_SEARCH_TOOL_NAME and self._web_search is not None:
            if web_searches >= profile.max_search_uses:
                return (
                    "Web search budget exhausted for this run; answer from the "
                    "evidence already gathered.",
                    web_searches,
                )
            web_searches += 1
            self._emit(events.SEARCH, f"Searching: {query}", query=query)
            return (
                self._run_web_search(query, digest_parts, sources, seen_urls),
                web_searches,
            )

        if name == DOCUMENT_SEARCH_TOOL_NAME and self._retriever is not None:
            return (
                self._run_document_search(query, digest_parts, sources, seen_refs),
                web_searches,
            )

        return f"Unknown or unavailable tool: {name}", web_searches

    def _run_web_search(self, query, digest_parts, sources, seen_urls) -> str:
        """Run one web search; harvest results into evidence + sources.

        Result snippets are truncated so the running conversation stays under
        the free-tier per-minute token limit (see config).
        """
        try:
            hits = self._web_search(query, WEB_SEARCH_MAX_RESULTS) or []
        except Exception as exc:  # noqa: BLE001 - one failure shouldn't kill the run
            # Resilient to a single tool failure: log and keep going (FR-AGT-8).
            self._emit(events.ERROR, f"Web search failed: {exc}", error=str(exc))
            return "The web search tool returned an error; try a different query."

        lines = []
        new = 0
        for hit in hits:
            url = hit.get("url", "")
            content = (hit.get("content", "") or "")[:WEB_RESULT_CHAR_LIMIT]
            title = hit.get("title", "")
            lines.append(f"[{title}] ({url}) {content}")
            if url and url not in seen_urls:
                seen_urls.add(url)
                sources.append({"url": url, "title": title})
                digest_parts.append(f"[web] {title}: {content}")
                new += 1
        self._emit(events.OBSERVATION, f"Found {new} new source(s)", new_sources=new)
        return "\n\n".join(lines) or "No results found for that query."

    def _run_document_search(self, query, digest_parts, sources, seen_refs) -> str:
        """Run one document search; harvest passages into evidence + sources."""
        self._emit(events.SEARCH, f"Searching documents: {query}", query=query)
        hits = self._retriever(query, RAG_TOP_K) or []

        lines = []
        for hit in hits:
            ref = hit.get("doc_ref", "")
            lines.append(f"[{ref}] ({hit.get('filename', '')}) {hit.get('text', '')}")
            if ref and ref not in seen_refs:
                seen_refs.add(ref)
                sources.append(
                    {"kind": "document", "doc_ref": ref, "filename": hit.get("filename", "")}
                )
                digest_parts.append(f"[doc {ref}] {hit.get('text', '')}")
        self._emit(
            events.OBSERVATION, f"Found {len(hits)} document passage(s)", new_sources=len(hits)
        )
        return "\n\n".join(lines) or "No matching passages found in the user's documents."

    # -- helpers ------------------------------------------------------------

    def _budget_exhausted(self, profile: DepthProfile, started: float) -> bool:
        if self._llm.usage.total_tokens >= profile.token_budget:
            return True
        if (time.monotonic() - started) >= profile.wall_clock_seconds:
            return True
        return False

    def _checkpoint(self):
        if self._should_cancel():
            self._emit(events.STATUS, "Cancellation requested; stopping")
            raise RunCancelled()

    def _emit(self, kind, message, **data):
        self._emitter.emit(ProgressEvent(kind=kind, message=message, data=data))


def _assistant_message(message) -> dict:
    """Convert a Groq assistant message back into a re-sendable dict."""
    out = {"role": "assistant", "content": message.content or ""}
    if message.tool_calls:
        out["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.function.name,
                    "arguments": call.function.arguments,
                },
            }
            for call in message.tool_calls
        ]
    return out


def _preview(text: str, limit: int = 200) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _format_source(i: int, s: dict) -> str:
    if s.get("kind") == "document":
        return f"[{i}] document: {s.get('filename', '')} (doc_ref {s.get('doc_ref', '')})"
    return f"[{i}] {s.get('title') or s.get('url', '')} - {s.get('url', '')}"
