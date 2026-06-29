"""Worker entrypoint: consume ``research.jobs`` and run the agent.

This is the production path for the worker tier (README architecture). It
bootstraps Django for ORM access, then consumes research jobs and drives each
one through :func:`worker.runner.process_job`. To exercise the agent without a
Kafka/Redis stack, use :mod:`worker.cli` instead.

    python -m worker.main
"""
import logging

from dotenv import load_dotenv

from worker import django_bootstrap

# Django must be configured before the ORM-backed modules below are imported.
load_dotenv()
django_bootstrap.setup()

from research.messaging import (  # noqa: E402
    DOCUMENTS_INGEST_TOPIC,
    RESEARCH_JOBS_TOPIC,
    get_consumer,
)

from worker.config import Settings  # noqa: E402
from worker.ingest import ingest_document  # noqa: E402
from worker.runner import process_job  # noqa: E402

logger = logging.getLogger("worker.main")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = Settings.from_env()

    topics = (RESEARCH_JOBS_TOPIC, DOCUMENTS_INGEST_TOPIC)
    consumer = get_consumer(*topics)
    logger.info("worker listening on %s", ", ".join(topics))
    try:
        for message in consumer:
            # Both handlers record their own failures; the guard is a backstop so
            # a single bad message can never take the consumer down.
            try:
                if message.topic == RESEARCH_JOBS_TOPIC:
                    process_job(message.value, settings)
                elif message.topic == DOCUMENTS_INGEST_TOPIC:
                    ingest_document(message.value)
            except Exception:  # pragma: no cover - defensive
                logger.exception("unhandled error processing %s message", message.topic)
    finally:
        consumer.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
