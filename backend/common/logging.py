"""Structured JSON logging shared by the API and worker (NFR-OBS-1, FR-ADM-2).

One line of JSON per event with a stable core (`ts`, `level`, `logger`, `msg`)
plus any ``extra=`` fields the call site attached — most importantly ``run_id``,
so a single run can be traced across the API and worker tiers.
"""
import json
import logging

# Standard LogRecord attributes; anything else on the record came from ``extra=``.
_RESERVED = set(logging.makeLogRecord({}).__dict__) | {"asctime", "message", "taskName"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Route the root logger through the JSON formatter (used by the worker; the
    API configures the same formatter via Django's LOGGING setting)."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
