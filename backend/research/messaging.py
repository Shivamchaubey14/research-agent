"""Kafka plumbing shared by the API (producer) and worker (consumer).

The API publishes research jobs to ``research.jobs``; the worker tier consumes
them and runs the agent. A run that fails terminally is routed to a dead-letter
topic so it is never silently lost (FR-RUN-7). Connection objects are created
lazily and cached per process.
"""
import json
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

RESEARCH_JOBS_TOPIC = "research.jobs"
RESEARCH_JOBS_DLQ = "research.jobs.dlq"
DOCUMENTS_INGEST_TOPIC = "documents.ingest"
CONSUMER_GROUP = "research-workers"

_producer = None


def _bootstrap_servers():
    return settings.KAFKA_BOOTSTRAP_SERVERS.split(",")


def get_producer():
    """Return a cached idempotent JSON producer (``acks=all``, retried)."""
    global _producer
    if _producer is None:
        from kafka import KafkaProducer  # imported lazily so settings load cheaply

        _producer = KafkaProducer(
            bootstrap_servers=_bootstrap_servers(),
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            acks="all",
            retries=3,
            linger_ms=10,
        )
    return _producer


def publish_job(topic, key, payload):
    """Produce ``payload`` to ``topic`` keyed by ``key`` and flush.

    Keying by run id keeps a run's messages on one partition (ordering); the
    flush makes delivery synchronous at the call site so callers see failures.
    """
    producer = get_producer()
    future = producer.send(topic, key=key, value=payload)
    producer.flush()
    future.get(timeout=10)


def get_consumer(*topics, group_id=CONSUMER_GROUP):
    """Return a JSON consumer subscribed to ``topics`` in ``group_id``.

    Offsets auto-commit: the handler owns error recovery (mark FAILED + DLQ),
    so an exception must not wedge the partition by replaying forever.
    """
    from kafka import KafkaConsumer

    return KafkaConsumer(
        *topics,
        bootstrap_servers=_bootstrap_servers(),
        group_id=group_id,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        key_deserializer=lambda k: k.decode("utf-8") if k else None,
        auto_offset_reset="earliest",
        enable_auto_commit=True,
    )
