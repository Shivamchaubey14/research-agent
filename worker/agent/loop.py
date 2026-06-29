"""The research agent loop: plan -> search -> verify -> cite (SRS §5.3).

The loop autonomously decomposes the question (FR-AGT-1), drives the Claude
tool-use interface to search the web (FR-AGT-2), iterates until the evidence is
sufficient or a hard ceiling is reached (FR-AGT-3), enforces token and
wall-clock budgets (FR-AGT-4), and synthesises a cited report whose claims are
grounded in retrieved sources (FR-AGT-5, FR-AGT-6). Every step emits a progress
event (FR-AGT-7).
"""
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from worker.agent import events, prompts
from worker.agent.events import ProgressEmitter, ProgressEvent
from worker.agent.llm import LLM, Usage
from worker.agent.schema import Plan, ReportDraft
from worker.config import (
    AGENT_POLICY_VERSION,
    DOCUMENT_SEARCH_TOOL_NAME,
    RAG_TOP_K,
    WEB_SEARCH_TOOL_NAME,
    WEB_SEARCH_TOOL_TYPE,
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

# Client-side tool exposed to the model when a retriever is available.
_DOCUMENT_SEARCH_TOOL = {
    "name": DOCUMENT_SEARCH_TOOL_NAME,
    "description": (
        "Search the user's uploaded documents for passages relevant to a query. "
        "Returns excerpts, each with a source reference (doc_ref). Use this to "
        "ground answers in the user's own files, alongside web search."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "What to look for."}
        },
        "required": ["query"],
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
        self._llm = LLM(settings.anthropic_api_key, settings.model)
        self._emitter = emitter or events.LoggingEmitter()
        self._should_cancel = should_cancel or (lambda: False)
        self._retriever = retriever

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
        """Drive the search tool loop; return (evidence digest, sources).

        Always has web search (a server tool); when a retriever is injected it
        also offers a client-side ``document_search`` tool over the user's
        uploaded documents, executing those calls and feeding results back.
        """
        tools = [
            {
                "type": WEB_SEARCH_TOOL_TYPE,
                "name": WEB_SEARCH_TOOL_NAME,
                "max_uses": profile.max_search_uses,
            }
        ]
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

        for turn in range(profile.max_research_turns):
            if self._budget_exhausted(profile, started):
                self._emit(events.STATUS, "Budget reached; wrapping up research")
                break
            self._checkpoint()

            message = self._llm.research_turn(
                system=prompts.RESEARCHER_SYSTEM,
                messages=messages,
                tools=tools,
                effort=profile.effort,
                max_tokens=profile.max_research_tokens,
            )
            self._consume_blocks(message.content, digest_parts, sources, seen_urls)
            messages.append({"role": "assistant", "content": message.content})

            if message.stop_reason == "pause_turn":
                # Server-side tool loop hit its limit; re-send to resume.
                continue
            if message.stop_reason == "tool_use":
                # The model called the client-side document_search tool; run it,
                # return the results, and let it continue.
                tool_results = self._run_document_search(
                    message.content, digest_parts, sources, seen_refs
                )
                if tool_results:
                    messages.append({"role": "user", "content": tool_results})
                    continue
                break  # nothing we can answer — avoid looping forever
            # end_turn / max_tokens / refusal: the research stage is done.
            break

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

    # -- helpers ------------------------------------------------------------

    def _consume_blocks(self, content, digest_parts, sources, seen_urls):
        """Emit events for each content block and harvest evidence + sources."""
        for block in content:
            btype = getattr(block, "type", None)
            if btype == "text":
                text = block.text.strip()
                if text:
                    digest_parts.append(text)
                    self._emit(events.REASONING, _preview(text))
            elif btype == "server_tool_use":
                query = (block.input or {}).get("query", "")
                self._emit(events.SEARCH, f"Searching: {query}", query=query)
            elif btype == "web_search_tool_result":
                self._harvest_results(block, sources, seen_urls)

    def _run_document_search(self, content, digest_parts, sources, seen_refs):
        """Execute document_search tool calls; return tool_result blocks.

        Harvests retrieved passages into the evidence digest and the source list
        (kind="document"), and returns one tool_result per tool_use block."""
        tool_results = []
        for block in content:
            if getattr(block, "type", None) != "tool_use":
                continue
            if block.name != DOCUMENT_SEARCH_TOOL_NAME:
                continue
            query = (block.input or {}).get("query", "")
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
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": "\n\n".join(lines)
                    or "No matching passages found in the user's documents.",
                }
            )
        return tool_results

    def _harvest_results(self, block, sources, seen_urls):
        results = getattr(block, "content", None)
        # An error surfaces as a single object, not a list (FR-AGT-8).
        if isinstance(results, list):
            new = 0
            for item in results:
                url = getattr(item, "url", None)
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                sources.append({"url": url, "title": getattr(item, "title", "") or ""})
                new += 1
            self._emit(events.OBSERVATION, f"Found {new} new source(s)", new_sources=new)
        else:
            code = getattr(results, "error_code", "unknown")
            # Resilient to a single tool failure: log and keep going (FR-AGT-8).
            self._emit(events.ERROR, f"Web search returned an error: {code}",
                       error_code=code)

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


def _preview(text: str, limit: int = 200) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _format_source(i: int, s: dict) -> str:
    if s.get("kind") == "document":
        return f"[{i}] document: {s.get('filename', '')} (doc_ref {s.get('doc_ref', '')})"
    return f"[{i}] {s.get('title') or s.get('url', '')} - {s.get('url', '')}"
