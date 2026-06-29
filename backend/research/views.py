from django.db import transaction
from django.db.models import (
    Avg,
    Count,
    DurationField,
    ExpressionWrapper,
    F,
    Sum,
)
from django.http import StreamingHttpResponse
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from . import streaming
from .models import Document, ResearchRun
from .permissions import IsOwner
from .serializers import (
    AdminRunSerializer,
    DocumentSerializer,
    RunCreateSerializer,
    RunDetailSerializer,
    RunListSerializer,
)
from .services import enqueue_document, enqueue_run

# Maps a terminal run status to the terminal SSE event kind, so a client that
# subscribes after the run finished (or after the event stream expired) still
# receives a closing event (FR-STR-4).
_TERMINAL_EVENT = {
    ResearchRun.Status.COMPLETED: streaming.COMPLETE,
    ResearchRun.Status.FAILED: streaming.FAILED,
    ResearchRun.Status.CANCELLED: streaming.CANCELLED,
}


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


class QueryParamJWTAuthentication(JWTAuthentication):
    """JWT auth that also accepts ``?token=`` for the SSE endpoint.

    The browser ``EventSource`` API cannot set an ``Authorization`` header, so
    the access token is passed as a query parameter for this one read-only,
    owner-scoped endpoint.
    """

    def authenticate(self, request):
        header_auth = super().authenticate(request)
        if header_auth is not None:
            return header_auth
        raw = request.query_params.get("token")
        if not raw:
            return None
        token = self.get_validated_token(raw)
        return self.get_user(token), token


class RunEventsView(APIView):
    """GET /api/v1/runs/{id}/events — live progress over SSE (FR-STR-1..4)."""

    authentication_classes = [QueryParamJWTAuthentication]
    permission_classes = [*APIView.permission_classes, IsOwner]
    throttle_classes = []  # a long-lived stream must not be rate-limited

    def get(self, request, pk):
        run = generics.get_object_or_404(
            ResearchRun.objects.filter(user=request.user), pk=pk
        )
        self.check_object_permissions(request, run)

        # Resume from the last id the client saw (FR-STR-3); else replay all.
        last_id = request.headers.get("Last-Event-ID") or request.query_params.get(
            "last_id", "0"
        )
        terminal_kind = _TERMINAL_EVENT.get(run.status) if run.is_terminal else None

        response = StreamingHttpResponse(
            self._frames(run.id, last_id, terminal_kind),
            content_type="text/event-stream",
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"  # disable nginx buffering for SSE
        return response

    @staticmethod
    def _frames(run_id, last_id, terminal_kind):
        for kind, frame in streaming.iter_events(run_id, last_id=last_id):
            if kind == streaming.STREAM_UNAVAILABLE:
                # The progress store can't serve streams (e.g. Redis < 5.0).
                yield streaming._sse_frame(
                    "0-0",
                    {
                        "kind": "error",
                        "message": "Live progress is unavailable (the progress store "
                        "does not support streams; Redis 5+ is required).",
                        "data": "{}",
                    },
                )
                return
            if frame is not None:
                yield frame
                continue
            # Idle tick. If the run already finished but its stream carried no
            # terminal event (e.g. it expired), synthesise one and close.
            if terminal_kind is not None:
                yield streaming._sse_frame(
                    "0-0",
                    {"kind": terminal_kind, "message": "Run already finished", "data": "{}"},
                )
                return
            yield streaming.heartbeat_frame()


class DocumentListCreateView(generics.ListCreateAPIView):
    """GET /api/v1/documents — list the caller's documents.
    POST /api/v1/documents — upload a document for RAG (FR-RAG-1)."""

    serializer_class = DocumentSerializer
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        return Document.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        document = serializer.save()
        # Dispatch ingestion only after the row + file are committed (FR-RAG-2).
        transaction.on_commit(lambda: enqueue_document(document))


class AdminMetricsView(APIView):
    """GET /api/v1/admin/metrics — operational metrics (FR-ADM-3, NFR-OBS-2)."""

    permission_classes = [IsAdminUser]
    throttle_classes = []

    def get(self, request):
        runs = ResearchRun.objects
        by_status = {
            row["status"]: row["n"]
            for row in runs.values("status").annotate(n=Count("id"))
        }
        S = ResearchRun.Status
        finished = sum(by_status.get(s, 0) for s in (S.COMPLETED, S.FAILED, S.CANCELLED))
        failed = by_status.get(S.FAILED, 0)

        # Average wall-clock latency of completed runs.
        latency = (
            runs.filter(status=S.COMPLETED, started_at__isnull=False, ended_at__isnull=False)
            .annotate(
                d=ExpressionWrapper(F("ended_at") - F("started_at"), output_field=DurationField())
            )
            .aggregate(avg=Avg("d"))["avg"]
        )

        totals = runs.aggregate(tokens=Sum("total_tokens"), cost=Sum("cost_usd"))
        return Response(
            {
                "runs": {
                    "total": sum(by_status.values()),
                    "by_status": by_status,
                    "queue_depth": by_status.get(S.QUEUED, 0),
                    "running": by_status.get(S.RUNNING, 0),
                },
                "error_rate": round(failed / finished, 4) if finished else 0.0,
                "avg_run_latency_seconds": latency.total_seconds() if latency else None,
                "token_spend": int(totals["tokens"] or 0),
                "cost_usd": float(totals["cost"] or 0),
                "worker_last_seen": streaming.worker_last_seen(),
            }
        )


class AdminRunListView(generics.ListAPIView):
    """GET /api/v1/admin/runs — inspect runs across users, FAILED first (FR-ADM-4).

    Defaults to failed runs; pass ``?status=`` to filter to any status.
    """

    permission_classes = [IsAdminUser]
    serializer_class = AdminRunSerializer
    throttle_classes = []

    def get_queryset(self):
        status_filter = self.request.query_params.get("status", ResearchRun.Status.FAILED)
        qs = ResearchRun.objects.select_related("user")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs
