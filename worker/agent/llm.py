"""Anthropic client wrapper with token + cost accounting (FR-RUN-6).

Centralises every call to the Claude API so usage can be accumulated in one
place. Research turns stream (large ``max_tokens`` plus the web-search server
loop would otherwise risk HTTP timeouts); the structured plan/synthesis calls
use ``messages.parse`` for schema-validated output.
"""
from dataclasses import dataclass
from typing import Type, TypeVar

import anthropic
from pydantic import BaseModel

from worker.config import MODEL_PRICING

T = TypeVar("T", bound=BaseModel)


@dataclass
class Usage:
    """Running token + cost totals for a single run (FR-RUN-6)."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_write_tokens
            + self.cache_read_tokens
        )

    def add(self, raw_usage) -> None:
        """Accumulate the ``usage`` block from an API response."""
        self.input_tokens += raw_usage.input_tokens or 0
        self.output_tokens += raw_usage.output_tokens or 0
        self.cache_write_tokens += getattr(raw_usage, "cache_creation_input_tokens", 0) or 0
        self.cache_read_tokens += getattr(raw_usage, "cache_read_input_tokens", 0) or 0

    def cost_usd(self, model: str) -> float:
        price = MODEL_PRICING.get(model, MODEL_PRICING["claude-opus-4-8"])
        per_in = price["input"] / 1_000_000
        per_out = price["output"] / 1_000_000
        return round(
            self.input_tokens * per_in
            + self.cache_write_tokens * per_in * 1.25
            + self.cache_read_tokens * per_in * 0.1
            + self.output_tokens * per_out,
            6,
        )


class LLM:
    """Thin wrapper over the Anthropic SDK that tracks usage as it goes."""

    def __init__(self, api_key: str, model: str):
        self._client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.usage = Usage()

    def parse(
        self,
        *,
        system: str,
        messages: list,
        schema: Type[T],
        effort: str,
        max_tokens: int,
    ) -> T:
        """Schema-constrained call used for planning and synthesis."""
        response = self._client.messages.parse(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            thinking={"type": "adaptive"},
            output_config={"effort": effort},
            messages=messages,
            output_format=schema,
        )
        self.usage.add(response.usage)
        if response.parsed_output is None:
            raise RuntimeError(
                f"structured output did not parse (stop_reason={response.stop_reason})"
            )
        return response.parsed_output

    def research_turn(
        self,
        *,
        system: str,
        messages: list,
        tools: list,
        effort: str,
        max_tokens: int,
    ):
        """One streamed research turn with the web-search tool available.

        Returns the final :class:`anthropic.types.Message`. Usage is accumulated.
        """
        with self._client.messages.stream(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            thinking={"type": "adaptive"},
            output_config={"effort": effort},
            tools=tools,
            messages=messages,
        ) as stream:
            message = stream.get_final_message()
        self.usage.add(message.usage)
        return message
