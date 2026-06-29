"""Extract text from an uploaded file and split it into overlapping chunks.

Supports PDF, plain text and Markdown (FR-RAG-1). Chunking is character-based
with a fixed overlap so a claim that straddles a boundary still appears whole in
at least one chunk; heavy libraries are imported lazily so the worker starts
without them installed until ingestion actually runs.
"""


def extract_text(path: str, content_type: str = "", filename: str = "") -> str:
    """Return the document's text. PDFs go through pypdf; everything else is
    read as UTF-8 (Markdown is just text)."""
    name = (filename or path).lower()
    is_pdf = name.endswith(".pdf") or "pdf" in (content_type or "")
    if is_pdf:
        from pypdf import PdfReader

        reader = PdfReader(path)
        return "\n".join((page.extract_text() or "") for page in reader.pages)

    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        return fh.read()


def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    """Split normalised text into ``size``-char chunks overlapping by ``overlap``."""
    text = " ".join(text.split())  # collapse whitespace/newlines
    if not text:
        return []
    if overlap >= size:
        overlap = size // 4

    chunks, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return chunks
