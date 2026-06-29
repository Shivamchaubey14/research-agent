"""Structured progress events (FR-AGT-7).

The agent emits an event for every plan, tool call, observation, verification
and status change. In Phase 2 these are consumed by a logging emitter; Phase 3
swaps in an emitter that publishes to Kafka/Redis for SSE fan-out (FR-STR-1)
without the agent code changing.
"""
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("worker.agent")


# Event kinds the loop emits, ordered roughly by lifecycle.
PLAN = "plan"
STATUS = "status"
SEARCH = "search"  # a web_search tool call (the query)
OBSERVATION = "observation"  # results returned by a tool
REASONING = "reasoning"  # the model's interim text between tool calls
VERIFICATION = "verification"  # grounding/citation check during synthesis
REPORT = "report"  # the final structured report
ERROR = "error"


@dataclass
class ProgressEvent:
    kind: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)


class ProgressEmitter:
    """Base emitter. Phase 3 subclasses this to publish to Kafka/Redis."""

    def emit(self, event: ProgressEvent) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class LoggingEmitter(ProgressEmitter):
    """Default emitter: writes events to the standard logger."""

    def emit(self, event: ProgressEvent) -> None:
        logger.info("agent.%s %s", event.kind, event.message, extra={"event": event.data})


class CallbackEmitter(ProgressEmitter):
    """Adapts any ``callable(ProgressEvent)`` into an emitter (CLI, tests)."""

    def __init__(self, callback):
        self._callback = callback

    def emit(self, event: ProgressEvent) -> None:
        self._callback(event)
