from django.db import transaction
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Document, ResearchRun
from .permissions import IsOwner
from .serializers import (
    DocumentSerializer,
    RunCreateSerializer,
    RunDetailSerializer,
    RunListSerializer,
)
from .services import enqueue_run


class RunListCreateView(generics.ListCreateAPIView):
    """GET /api/v1/runs — list the caller's runs (FR-RPT-3).
    POST /api/v1/runs — submit a question; returns a QUEUED run (FR-RUN-3)."""

    throttle_scope = "runs"

    def get_queryset(self):
        # Scoped to the caller — a user never sees another user's runs (FR-AUTH-5).
        return ResearchRun.objects.filter(user=self.request.user)

    def get_serializer_class(self):
        return RunCreateSerializer if self.request.method == "POST" else RunListSerializer

    def perform_create(self, serializer):
        run = serializer.save()
        # Dispatch only after the row is committed, so the worker can never
        # consume a job for a run it cannot yet read.
        transaction.on_commit(lambda: enqueue_run(run))


class RunDetailView(generics.RetrieveAPIView):
    """GET /api/v1/runs/{id} — fetch a run and its final report."""

    serializer_class = RunDetailSerializer
    permission_classes = [*generics.RetrieveAPIView.permission_classes, IsOwner]

    def get_queryset(self):
        return ResearchRun.objects.filter(user=self.request.user).select_related(
            "report"
        )


class RunCancelView(APIView):
    """POST /api/v1/runs/{id}/cancel — request cancellation (FR-RUN-5)."""

    permission_classes = [*APIView.permission_classes, IsOwner]

    def post(self, request, pk):
        run = generics.get_object_or_404(
            ResearchRun.objects.filter(user=request.user), pk=pk
        )
        self.check_object_permissions(request, run)

        if run.is_terminal:
            return Response(
                {"detail": f"Run is already {run.status}; cannot cancel."},
                status=status.HTTP_409_CONFLICT,
            )

        run.status = ResearchRun.Status.CANCELLED
        run.ended_at = timezone.now()
        run.save(update_fields=["status", "ended_at"])
        # The worker observes the CANCELLED status and stops at the next safe
        # checkpoint (FR-RUN-5); full cooperative cancellation lands in Phase 3.
        return Response(RunDetailSerializer(run).data)


class DocumentListCreateView(generics.ListCreateAPIView):
    """GET /api/v1/documents — list the caller's documents.
    POST /api/v1/documents — upload a document for RAG (FR-RAG-1)."""

    serializer_class = DocumentSerializer
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        return Document.objects.filter(user=self.request.user)
