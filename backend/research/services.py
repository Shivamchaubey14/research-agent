"""Job dispatch boundary.

Submitting a run publishes a job to Kafka for the worker tier to consume and
seeds a ``queued`` progress event so a client that subscribes immediately sees
the run before the worker has picked it up. The QUEUED row is already persisted
and returned by the view (FR-RUN-3); dispatch happens after commit.
"""
import logging

from . import streaming
from .messaging import RESEARCH_JOBS_TOPIC, publish_job

logger = logging.getLogger(__name__)


def enqueue_run(run):
    """Publish a research job for the worker tier to consume.

    Args:
        run: the persisted :class:`~research.models.ResearchRun`.

    A messaging failure is logged and the run is left QUEUED rather than marked
    FAILED — the job can be re-dispatched without losing the user's submission.
    """
    payload = {
        "run_id": str(run.id),
        "user_id": run.user_id,
        "question": run.question,
        "depth": run.depth,
    }
    try:
        publish_job(RESEARCH_JOBS_TOPIC, key=str(run.id), payload=payload)
        streaming.publish_event(run.id, "queued", "Run queued for the agent")
        logger.info("run.enqueued", extra={"run_id": str(run.id), "topic": RESEARCH_JOBS_TOPIC})
    except Exception:
        logger.exception("run.enqueue_failed", extra={"run_id": str(run.id)})
