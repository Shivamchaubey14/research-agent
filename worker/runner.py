"""Per-job orchestration: drive one ResearchRun through its lifecycle.

Consumes a job, transitions the run QUEUED -> RUNNING -> (COMPLETED | FAILED |
CANCELLED) recording timestamps (FR-RUN-4), runs the agent with progress fanned
out over Redis, persists the report and citations, accounts tokens and cost
(FR-RUN-6), and routes a terminally failed run to the dead-letter topic
(FR-RUN-7). Requires :func:`worker.django_bootstrap.setup` to have run.
"""
import logging

from django.db import transaction
from django.utils import timezone

from research import streaming
from research.messaging import RESEARCH_JOBS_DLQ, publish_job
from research.models import Citation, Document, Report, ResearchRun

from worker.agent import ResearchAgent
from worker.agent.loop import RunCancelled
from worker.bus import RedisProgressEmitter
from worker.config import RAG_TOP_K, Settings
from worker.rag import store

logger = logging.getLogger("worker.runner")

_VALID_CITATION_KINDS = {c.value for c in Citation.Kind}


def process_job(job: dict, settings: Settings) -> None:
    """Handle a single ``research.jobs`` message. Never raises."""
    run_id = job.get("run_id")
    try:
        run = ResearchRun.objects.get(id=run_id)
    except ResearchRun.DoesNotExist:
        logger.warning("job for unknown run; dropping", extra={"run_id": run_id})
        return

    # Cancelled before pickup, or a duplicate delivery of a finished run.
    if run.is_terminal:
        logger.info("run already terminal; skipping", extra={"run_id": run_id})
        return

    run.status = ResearchRun.Status.RUNNING
    run.started_at = timezone.now()
    run.save(update_fields=["status", "started_at"])
    streaming.publish_event(run_id, "status", "Research started")

    agent = ResearchAgent(
        settings,
        emitter=RedisProgressEmitter(run_id),
        should_cancel=lambda: _cancel_requested(run_id),
        retriever=_build_retriever(run.user_id),
    )

    try:
        result = agent.run(run.question, depth=run.depth)
    except RunCancelled:
        _finalize_cancelled(run)
    except Exception as exc:  # noqa: BLE001 - any failure must be recorded, not lost
        _finalize_failed(run, exc, job)
    else:
        _persist_success(run, result)


def _build_retriever(user_id):
    """Return a Qdrant-backed document retriever, or None if the user has no
    ingested documents (keeps web-only runs unchanged — FR-RAG-3)."""
    has_docs = Document.objects.filter(
        user_id=user_id, status=Document.Status.READY
    ).exists()
    if not has_docs:
        return None
    return lambda query, top_k=RAG_TOP_K: store.search(user_id, query, top_k)


def _cancel_requested(run_id) -> bool:
    """Cheap status-only probe used at the agent's safe checkpoints (FR-RUN-5)."""
    return ResearchRun.objects.filter(
        id=run_id, status=ResearchRun.Status.CANCELLED
    ).exists()


def _persist_success(run: ResearchRun, result) -> None:
    sections = [{"heading": s.heading, "content": s.content} for s in result.report.sections]
    with transaction.atomic():
        report = Report.objects.create(
            run=run, summary=result.report.summary, sections=sections
        )
        Citation.objects.bulk_create(_citation_rows(report, result.report.citations))
        run.status = ResearchRun.Status.COMPLETED
        run.total_tokens = result.usage.total_tokens
        run.cost_usd = result.cost_usd
        run.ended_at = timezone.now()
        run.save(update_fields=["status", "total_tokens", "cost_usd", "ended_at"])

    streaming.publish_event(
        run.id,
        streaming.COMPLETE,
        "Report ready",
        data={
            "sections": len(sections),
            "citations": len(report.citations.all()),
            "total_tokens": run.total_tokens,
            "cost_usd": float(run.cost_usd),
        },
    )
    logger.info("run.completed", extra={"run_id": str(run.id)})


def _citation_rows(report, citations):
    """Build Citation rows, dropping duplicate markers (unique per report)."""
    rows, seen = [], set()
    for c in citations:
        if c.marker in seen:
            continue
        seen.add(c.marker)
        kind = c.kind if c.kind in _VALID_CITATION_KINDS else Citation.Kind.WEB
        rows.append(
            Citation(
                report=report,
                marker=c.marker,
                kind=kind,
                title=c.title[:512],
                url=c.url[:1024],
                doc_ref=c.doc_ref[:255],
                snippet=c.snippet,
            )
        )
    return rows


def _finalize_cancelled(run: ResearchRun) -> None:
    run.refresh_from_db(fields=["status"])
    if not run.is_terminal:
        run.status = ResearchRun.Status.CANCELLED
        run.ended_at = timezone.now()
        run.save(update_fields=["status", "ended_at"])
    streaming.publish_event(run.id, streaming.CANCELLED, "Run cancelled")
    logger.info("run.cancelled", extra={"run_id": str(run.id)})


def _finalize_failed(run: ResearchRun, exc: Exception, job: dict) -> None:
    logger.exception("run.failed", extra={"run_id": str(run.id)})
    run.refresh_from_db(fields=["status"])
    if not run.is_terminal:  # a cancel may have raced in
        run.status = ResearchRun.Status.FAILED
        run.error = str(exc)[:2000]
        run.ended_at = timezone.now()
        run.save(update_fields=["status", "error", "ended_at"])
        streaming.publish_event(
            run.id, streaming.FAILED, "Run failed", data={"error": str(exc)[:500]}
        )
    # Route to the dead-letter topic for inspection/replay (FR-RUN-7).
    try:
        publish_job(RESEARCH_JOBS_DLQ, key=str(run.id), payload={**job, "error": str(exc)[:500]})
    except Exception:  # pragma: no cover - DLQ is best-effort
        logger.warning("failed to write to DLQ", extra={"run_id": str(run.id)})
