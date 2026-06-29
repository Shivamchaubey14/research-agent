"""Qdrant vector store for document chunks (FR-RAG-2, FR-RAG-5).

Embeddings are computed locally by fastembed via qdrant-client's ``add`` helper,
so there is no embedding API key. Each chunk keeps a resolvable reference back
to its source (``document_id#chunk_index``) and a ``user_id`` so retrieval can
be scoped to the owner (FR-AUTH-5). The client and model load lazily on first
use. Retrieval (``query``) lands in the next step.
"""
import uuid

from django.conf import settings

from worker.config import EMBED_MODEL, QDRANT_COLLECTION

_client = None


def get_client():
    global _client
    if _client is None:
        from qdrant_client import QdrantClient

        client = QdrantClient(url=settings.QDRANT_URL)
        client.set_model(EMBED_MODEL)  # fastembed model used by add()/query()
        _client = client
    return _client


def _chunk_id(document_id, index) -> str:
    # Deterministic id so re-ingesting a document overwrites its chunks rather
    # than duplicating them.
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{document_id}:{index}"))


def upsert_chunks(document_id, user_id, filename, chunks, client=None) -> int:
    """Embed and upsert chunks; returns the number stored. Auto-creates the
    collection sized to the embedding model on first call."""
    client = client or get_client()
    ids = [_chunk_id(document_id, i) for i in range(len(chunks))]
    metadata = [
        {
            "user_id": user_id,
            "document_id": str(document_id),
            "filename": filename,
            "chunk_index": i,
            "doc_ref": f"{document_id}#{i}",  # resolvable source ref (FR-RAG-5)
            "text": chunks[i],
        }
        for i in range(len(chunks))
    ]
    client.add(
        collection_name=QDRANT_COLLECTION,
        documents=chunks,
        metadata=metadata,
        ids=ids,
    )
    return len(chunks)


def search(user_id, query, top_k, client=None) -> list[dict]:
    """Return the top-k chunks most relevant to ``query``, scoped to ``user_id``.

    Scoping by a ``user_id`` payload filter enforces that a user only ever
    retrieves their own documents (FR-RAG-3, FR-AUTH-5). Returns [] if the
    collection does not exist yet (no documents ingested).
    """
    client = client or get_client()
    from qdrant_client import models as qmodels

    try:
        hits = client.query(
            collection_name=QDRANT_COLLECTION,
            query_text=query,
            query_filter=qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="user_id", match=qmodels.MatchValue(value=user_id)
                    )
                ]
            ),
            limit=top_k,
        )
    except Exception:
        return []

    results = []
    for hit in hits:
        meta = getattr(hit, "metadata", None) or {}
        results.append(
            {
                "text": meta.get("text", getattr(hit, "document", "") or ""),
                "doc_ref": meta.get("doc_ref", ""),
                "filename": meta.get("filename", ""),
                "score": getattr(hit, "score", 0.0),
            }
        )
    return results
