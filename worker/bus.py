"""Bridge the agent's progress events onto the Redis stream (FR-AGT-7 -> FR-STR-1).

The agent emits framework-agnostic :class:`ProgressEvent` objects; this emitter
forwards each one to the run's Redis stream via the backend's shared
``research.streaming`` helpers, so the SSE endpoint can fan them out unchanged.
Requires :func:`worker.django_bootstrap.setup` to have run.
"""
from research import streaming

from worker.agent.events import ProgressEmitter, ProgressEvent


class RedisProgressEmitter(ProgressEmitter):
    """Publishes agent progress events to a run's Redis stream."""

    def __init__(self, run_id, client=None):
        self._run_id = run_id
        self._client = client or streaming.get_redis()

    def emit(self, event: ProgressEvent) -> None:
        # Terminal events (complete/failed/cancelled) are published by the
        # runner once the DB is updated; agent-level events are all interim.
        streaming.publish_event(
            self._run_id,
            event.kind,
            event.message,
            data=event.data,
            client=self._client,
        )
