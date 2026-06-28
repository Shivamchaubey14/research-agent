"""Job dispatch boundary.

In Phase 1 the API persists a run and records the intent to dispatch it. The
actual Kafka producer and the agent worker that consumes ``research.jobs`` are
wired in Phase 3; until then this is a logged no-op so the API contract
(QUEUED run is returned immediately — FR-RUN-3) is already correct.
"""
import logging

logger = logging.getLogger(__name__)

RESEARCH_JOBS_TOPIC = "research.jobs"


def enqueue_run(run):
    """Publish a research job for the worker tier to consume.

    Args:
        run: the persisted :class:`~research.models.ResearchRun`.
    """
    # Phase 3 will replace this with a Kafka produce to RESEARCH_JOBS_TOPIC.
    logger.info(
        "run.enqueued",
        extra={"run_id": str(run.id), "topic": RESEARCH_JOBS_TOPIC},
    )
