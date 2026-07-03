"""Groq client wrapper with token + cost accounting (FR-RUN-6).

Centralises every call to the Groq API so usage can be accumulated in one
place. Groq speaks the OpenAI chat-completions dialect: the structured
plan/synthesis/judge calls constrain output with a JSON schema (validated
against the Pydantic model), and research turns expose client-side tools
(web + document search) that the loop executes and feeds back.
"""
import json
import re
import time
from dataclasses import dataclass
from typing import Type, TypeVar

from groq import APIStatusError, Groq
from pydantic import BaseModel

from worker.config import (
    DEFAULT_MODEL,
    EFFORT_MAP,
    MODEL_PRICING,
    supports_reasoning_effort,
)

T = TypeVar("T", bound=BaseModel)

# Groq's free tier is tightly rate-limited (e.g. 8k tokens/minute), so a
# multi-step run can trip the per-minute limit even when each request is small.
# Rather than fail the run, wait out the window and retry a few times.
_RATE_LIMIT_RETRIES = 4
_DEFAULT_RATE_LIMIT_WAIT = 20.0  # seconds, if the API doesn't suggest one


@dataclass
class Usage:
    """Running token + cost totals for a single run (FR-RUN-6).

    Groq reports only prompt/completion token counts (no separate cache-token
    accounting), so the totals are a straight input/output split.
    """

    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def add(self, raw_usage) -> None:
        """Accumulate the ``usage`` block from an API response."""
        if raw_usage is None:
            return
        self.input_tokens += getattr(raw_usage, "prompt_tokens", 0) or 0
        self.output_tokens += getattr(raw_usage, "completion_tokens", 0) or 0

    def cost_usd(self, model: str) -> float:
        price = MODEL_PRICING.get(model, MODEL_PRICING[DEFAULT_MODEL])
        per_in = price["input"] / 1_000_000
        per_out = price["output"] / 1_000_000
        return round(self.input_tokens * per_in + self.output_tokens * per_out, 6)


class LLM:
    """Thin wrapper over the Groq SDK that tracks usage as it goes."""

    def __init__(self, api_key: str, model: str):
        self._client = Groq(api_key=api_key)
        self.model = model
        self.usage = Usage()

    def _effort_kwargs(self, effort: str) -> dict:
        """``reasoning_effort`` only for models that accept it (see config)."""
        if effort and supports_reasoning_effort(self.model):
            return {"reasoning_effort": EFFORT_MAP.get(effort, "medium")}
        return {}

    def _create(self, **kwargs):
        """Call chat.completions.create, waiting out free-tier rate limits.

        A 429 is a per-minute rate limit: wait for the window to clear and
        retry. A 413 ("request too large") means this single request exceeds the
        per-minute token ceiling — retrying can't help, so it surfaces
        immediately (the config keeps requests small to avoid this).
        """
        for attempt in range(_RATE_LIMIT_RETRIES + 1):
            try:
                return self._client.chat.completions.create(**kwargs)
            except APIStatusError as exc:
                if exc.status_code == 429 and attempt < _RATE_LIMIT_RETRIES:
                    time.sleep(_retry_after_seconds(exc))
                    continue
                raise
        # Unreachable; the loop either returns or raises.
        raise RuntimeError("rate-limit retry loop exhausted")

    def parse(
        self,
        *,
        system: str,
        messages: list,
        schema: Type[T],
        effort: str,
        max_tokens: int,
    ) -> T:
        """Schema-constrained call used for planning, synthesis and judging.

        Groq's non-strict ``json_schema`` mode is unreliable across the free
        models (they sometimes echo the schema instead of an instance), so we
        use plain JSON-object mode, describe the schema in the prompt, and
        validate the result against the Pydantic model — which also fills in
        defaults for optional fields.
        """
        instruction = (
            "Respond with a single JSON object that conforms to this JSON "
            "Schema. Output only the JSON instance (the actual values), not the "
            "schema itself, and no surrounding prose:\n"
            + json.dumps(schema.model_json_schema())
        )
        # Structured calls need reliable JSON output, not deep chain-of-thought.
        # A high reasoning_effort can exhaust the (small, free-tier) token budget
        # on reasoning before any JSON is emitted, which the API then rejects as
        # json_validate_failed with an empty generation. Keep reasoning low here
        # regardless of the run's depth; ``effort`` still drives research turns.
        response = self._create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": f"{system}\n\n{instruction}"},
                *messages,
            ],
            response_format={"type": "json_object"},
            **self._effort_kwargs("low"),
        )
        self.usage.add(response.usage)
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError(
                "structured output was empty "
                f"(finish_reason={response.choices[0].finish_reason})"
            )
        return schema.model_validate_json(content)

    def chat(
        self,
        *,
        system: str,
        messages: list,
        tools: list,
        effort: str,
        max_tokens: int,
    ):
        """One research turn with the client-side tools available.

        Returns the assistant ``message`` (OpenAI shape: ``.content`` text plus
        optional ``.tool_calls``). Usage is accumulated. The loop is responsible
        for executing any tool calls and continuing the conversation.
        """
        kwargs = dict(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "system", "content": system}, *messages],
            **self._effort_kwargs(effort),
        )
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        response = self._create(**kwargs)
        self.usage.add(response.usage)
        return response.choices[0].message


def _retry_after_seconds(exc: APIStatusError) -> float:
    """Best-effort wait time from a Groq rate-limit error.

    Prefers the ``retry-after`` header, then a "try again in 12.3s" hint in the
    message, and finally a fixed fallback.
    """
    retry_after = exc.response.headers.get("retry-after") if exc.response else None
    if retry_after:
        try:
            return float(retry_after)
        except ValueError:
            pass
    match = re.search(r"try again in ([\d.]+)s", str(exc))
    if match:
        return float(match.group(1)) + 1.0  # small cushion past the window
    return _DEFAULT_RATE_LIMIT_WAIT
