from rest_framework import serializers

from .models import Citation, Document, Report, ResearchRun


class CitationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Citation
        fields = ["id", "marker", "kind", "title", "url", "doc_ref", "snippet"]
        read_only_fields = fields


class ReportSerializer(serializers.ModelSerializer):
    citations = CitationSerializer(many=True, read_only=True)

    class Meta:
        model = Report
        fields = ["id", "summary", "sections", "citations", "created_at"]
        read_only_fields = fields


class RunListSerializer(serializers.ModelSerializer):
    """Compact representation for the history list (FR-RPT-3)."""

    class Meta:
        model = ResearchRun
        fields = [
            "id", "question", "depth", "status",
            "total_tokens", "cost_usd", "created_at", "ended_at",
        ]
        read_only_fields = fields


class RunDetailSerializer(serializers.ModelSerializer):
    """Full run including the final report when present."""

    report = ReportSerializer(read_only=True)

    class Meta:
        model = ResearchRun
        fields = [
            "id", "question", "depth", "status",
            "total_tokens", "cost_usd", "error",
            "created_at", "started_at", "ended_at", "report",
        ]
        read_only_fields = fields


class RunCreateSerializer(serializers.ModelSerializer):
    """Submission payload (FR-RUN-1, FR-RUN-2)."""

    class Meta:
        model = ResearchRun
        fields = ["id", "question", "depth", "status", "created_at"]
        read_only_fields = ["id", "status", "created_at"]

    def validate_question(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("A question is required.")
        return value

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)


class DocumentSerializer(serializers.ModelSerializer):
    """Document upload metadata (FR-RAG-1, FR-RAG-6).

    The binary parse/chunk/embed pipeline arrives in Phase 5; here we accept the
    file, record its metadata and mark it PROCESSING.
    """

    file = serializers.FileField(write_only=True)

    class Meta:
        model = Document
        fields = [
            "id", "file", "filename", "content_type",
            "size_bytes", "status", "chunk_count", "created_at",
        ]
        read_only_fields = [
            "id", "filename", "content_type", "size_bytes",
            "status", "chunk_count", "created_at",
        ]

    def create(self, validated_data):
        upload = validated_data.pop("file")
        # Persist the bytes (FileField) so the worker can ingest them; the run
        # stays PROCESSING until ingestion completes (FR-RAG-6).
        return Document.objects.create(
            user=self.context["request"].user,
            file=upload,
            filename=upload.name,
            content_type=getattr(upload, "content_type", "") or "",
            size_bytes=upload.size,
            status=Document.Status.PROCESSING,
        )
