"""Ingest one uploaded document into the vector store.

Parses the file, chunks it, embeds and upserts the chunks into Qdrant, then
flips the document to READY with its chunk count (or FAILED with an error),
giving the per-document ingestion status the API reports (FR-RAG-6). Requires
:func:`worker.django_bootstrap.setup` to have run.
"""
import logging

from research.models import Document

from worker.config import CHUNK_OVERLAP, CHUNK_SIZE
from worker.rag import chunking, store

logger = logging.getLogger("worker.ingest")


def ingest_document(job: dict) -> None:
    """Handle a single ``documents.ingest`` message. Never raises."""
    doc_id = job.get("document_id")
    try:
        document = Document.objects.get(id=doc_id)
    except Document.DoesNotExist:
        logger.warning("ingest job for unknown document; dropping", extra={"document_id": doc_id})
        return

    try:
        document.status = Document.Status.PROCESSING
        document.save(update_fields=["status"])

        if not document.file:
            raise ValueError("no file stored for document")

        text = chunking.extract_text(
            document.file.path, document.content_type, document.filename
        )
        chunks = chunking.chunk_text(text, CHUNK_SIZE, CHUNK_OVERLAP)
        if not chunks:
            raise ValueError("no extractable text in document")

        count = store.upsert_chunks(
            document.id, document.user_id, document.filename, chunks
        )

        document.chunk_count = count
        document.status = Document.Status.READY
        document.error = ""
        document.save(update_fields=["chunk_count", "status", "error"])
        logger.info("document.ingested", extra={"document_id": str(document.id), "chunks": count})
    except Exception as exc:  # noqa: BLE001 - record failure, don't crash the worker
        logger.exception("document.ingest_failed", extra={"document_id": str(document.id)})
        document.status = Document.Status.FAILED
        document.error = str(exc)[:2000]
        document.save(update_fields=["status", "error"])
