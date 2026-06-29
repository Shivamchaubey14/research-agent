"""Worker entrypoint: consume ``research.jobs`` and run the agent.

This is the production path for the worker tier (README architecture). It
bootstraps Django for ORM access, then consumes research jobs and drives each
one through :func:`worker.runner.process_job`. To exercise the agent without a
Kafka/Redis stack, use :mod:`worker.cli` instead.

    python -m worker.main
"""
import logging
import os
from datetime import datetime, timezone

from dotenv import load_dotenv

from worker import django_bootstrap

# Django must be configured before the ORM-backed modules below are imported.
load_dotenv()
django_bootstrap.setup()

from common.logging import configure_logging  # noqa: E402
from research import streaming  # noqa: E402
from research.messaging import (  # noqa: E402
    DOCUMENTS_INGEST_TOPIC,
    RESEARCH_JOBS_TOPIC,
    get_consumer,
)

from worker.config import Settings  # noqa: E402
from worker.ingest import ingest_document  # noqa: E402
from worker.runner import process_job  # noqa: E402

logger = logging.getLogger("worker.main")


def _heartbeat() -> None:
    streaming.worker_heartbeat(datetime.now(timezone.utc).isoformat())


def main() -> int:
    # Same structured JSON logging as the API (NFR-OBS-1).
    configure_logging(os.environ.get("LOG_LEVEL", "INFO"))
    settings = Settings.from_env()

    topics = (RESEARCH_JOBS_TOPIC, DOCUMENTS_INGEST_TOPIC)
    consumer = get_consumer(*topics)
    _heartbeat()
    logger.info("worker listening", extra={"topics": list(topics)})
    try:
        for message in consumer:
            _heartbeat()
            # Both handlers record their own failures; the guard is a backstop so
            # a single bad message can never take the consumer down.
            try:
                if message.topic == RESEARCH_JOBS_TOPIC:
                    process_job(message.value, settings)
                elif message.topic == DOCUMENTS_INGEST_TOPIC:
                    ingest_document(message.value)
            except Exception:  # pragma: no cover - defensive
                logger.exception("unhandled error processing message", extra={"topic": message.topic})
    finally:
        consumer.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
