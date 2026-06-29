import uuid

from django.conf import settings
from django.db import models


class ResearchRun(models.Model):
    """One end-to-end execution of the research agent (Figure 7 — ResearchRun).

    The lifecycle QUEUED -> RUNNING -> (COMPLETED | FAILED | CANCELLED) is
    enforced at the application layer (FR-RUN-4, Figure 10).
    """

    class Status(models.TextChoices):
        QUEUED = "QUEUED", "Queued"
        RUNNING = "RUNNING", "Running"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"
        CANCELLED = "CANCELLED", "Cancelled"

    class Depth(models.TextChoices):
        QUICK = "quick", "Quick"
        STANDARD = "standard", "Standard"
        DEEP = "deep", "Deep"

    # A UUID public identifier so run ids are not guessable/enumerable.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="runs",
    )
    question = models.CharField(max_length=2000)  # FR-RUN-1
    depth = models.CharField(
        max_length=16, choices=Depth.choices, default=Depth.STANDARD
    )  # FR-RUN-2
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.QUEUED, db_index=True
    )

    # Budget accounting (FR-RUN-6).
    total_tokens = models.PositiveIntegerField(default=0)
    cost_usd = models.DecimalField(max_digits=10, decimal_places=4, default=0)

    error = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]  # newest first (FR-RPT-3)
        indexes = [models.Index(fields=["user", "-created_at"])]

    def __str__(self):
        return f"{self.id} ({self.status})"

    @property
    def is_terminal(self):
        return self.status in {
            self.Status.COMPLETED,
            self.Status.FAILED,
            self.Status.CANCELLED,
        }


class Report(models.Model):
    """Structured, immutable final output of a run (Figure 7 — Report).

    Reports are written once and never mutated; a re-run creates a new run
    rather than editing history (SRS §6.2 integrity rules).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.OneToOneField(
        ResearchRun, on_delete=models.CASCADE, related_name="report"
    )
    summary = models.TextField(blank=True)
    # Ordered list of {heading, content} section objects.
    sections = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Report for {self.run_id}"


class Citation(models.Model):
    """A resolvable source backing a claim in a report (Figure 7 — Citation)."""

    class Kind(models.TextChoices):
        WEB = "web", "Web"
        DOCUMENT = "document", "Document"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    report = models.ForeignKey(
        Report, on_delete=models.CASCADE, related_name="citations"
    )
    marker = models.PositiveIntegerField()  # inline citation number, e.g. [1]
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.WEB)
    title = models.CharField(max_length=512, blank=True)
    # Either a web URL or a "document_id#chunk" reference (FR-RPT-2, FR-RAG-5).
    url = models.URLField(max_length=1024, blank=True)
    doc_ref = models.CharField(max_length=255, blank=True)
    snippet = models.TextField(blank=True)

    class Meta:
        ordering = ["marker"]
        unique_together = [("report", "marker")]

    def __str__(self):
        return f"[{self.marker}] {self.title}"


class Document(models.Model):
    """A user-uploaded source for RAG; embeddings live in Qdrant keyed by id
    (Figure 7 — Document, SRS §6.2)."""

    class Status(models.TextChoices):
        PROCESSING = "processing", "Processing"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    # The stored upload; the worker reads this to parse, chunk and embed it.
    file = models.FileField(upload_to="documents/", blank=True)
    filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100, blank=True)
    size_bytes = models.PositiveBigIntegerField(default=0)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PROCESSING
    )  # FR-RAG-6
    chunk_count = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "-created_at"])]

    def __str__(self):
        return self.filename
