"""Redis-backed progress event stream (FR-STR-1..4).

The worker writes one event per agent step into a per-run Redis stream; the SSE
endpoint reads that stream and pushes events to the browser. A Redis *stream*
(not pub/sub) is used deliberately: it preserves order (FR-STR-2), gives every
event a monotonic id so a reconnecting client can resume from the last one it
saw (FR-STR-3), and retains history so a late subscriber still gets the whole
run. Each run ends with exactly one terminal event (FR-STR-4).
"""
import json
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

# Terminal event kinds — the stream ends after one of these is delivered.
COMPLETE = "complete"
FAILED = "failed"
CANCELLED = "cancelled"
TERMINAL_KINDS = frozenset({COMPLETE, FAILED, CANCELLED})

# Cap stream length and expire idle streams so Redis does not grow unbounded.
_MAX_EVENTS = 2000
_TTL_SECONDS = 24 * 60 * 60

_redis = None


def get_redis():
    """Return a cached, text-mode Redis client."""
    global _redis
    if _redis is None:
        import redis  # imported lazily

        _redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


def stream_key(run_id) -> str:
    return f"run:{run_id}:events"


def publish_event(run_id, kind, message, data=None, terminal=False, client=None) -> str:
    """Append an event to the run's stream; return its stream id.

    ``terminal`` is implied for terminal kinds. Failures are swallowed and
    logged: losing a progress event must never fail the run itself.
    """
    client = client or get_redis()
    is_terminal = terminal or kind in TERMINAL_KINDS
    key = stream_key(run_id)
    try:
        event_id = client.xadd(
            key,
            {
                "kind": kind,
                "message": message,
                "data": json.dumps(data or {}),
                "terminal": "1" if is_terminal else "0",
            },
            maxlen=_MAX_EVENTS,
            approximate=True,
        )
        client.expire(key, _TTL_SECONDS)
        return event_id
    except Exception:  # pragma: no cover - best-effort fan-out
        logger.warning("failed to publish progress event", extra={"run_id": str(run_id)})
        return ""


def iter_events(run_id, last_id="0", block_ms=15000, client=None):
    """Yield events for a run, oldest first, then block for new ones.

    Yields ``(kind, sse_payload)`` tuples; on each idle timeout yields
    ``(None, None)`` so the caller can emit an SSE heartbeat. Stops after a
    terminal event. ``last_id="0"`` replays the whole stream; pass the last id a
    client received to resume (FR-STR-3).
    """
    client = client or get_redis()
    key = stream_key(run_id)
    cursor = last_id or "0"
    while True:
        try:
            response = client.xread({key: cursor}, count=50, block=block_ms)
        except Exception:  # pragma: no cover - transient Redis blip
            logger.warning("redis xread failed", extra={"run_id": str(run_id)})
            yield None, None
            continue

        if not response:
            yield None, None  # heartbeat tick
            continue

        _, entries = response[0]
        for event_id, fields in entries:
            cursor = event_id
            yield fields["kind"], _sse_frame(event_id, fields)
            if fields.get("terminal") == "1":
                return


def _sse_frame(event_id, fields) -> str:
    """Render one stream entry as a Server-Sent Events frame."""
    payload = {"message": fields.get("message", ""), **json.loads(fields.get("data") or "{}")}
    return (
        f"id: {event_id}\n"
        f"event: {fields['kind']}\n"
        f"data: {json.dumps(payload)}\n\n"
    )


def heartbeat_frame() -> str:
    """An SSE comment line that keeps the connection alive through proxies."""
    return ": keepalive\n\n"
