import urllib.request

from django.conf import settings
from django.db import connection
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.response import Response


@api_view(["GET"])
@authentication_classes([])
@permission_classes([])
@throttle_classes([])
def health(request):
    """Liveness probe (FR-ADM-1): process is up and the database is reachable.
    Returns 200 when the database responds, 503 otherwise."""
    checks = {"database": "ok"}
    status = 200
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:  # pragma: no cover - exercised only on outage
        checks["database"] = "unavailable"
        status = 503

    return Response(
        {"status": "ok" if status == 200 else "degraded", "checks": checks},
        status=status,
    )


@api_view(["GET"])
@authentication_classes([])
@permission_classes([])
@throttle_classes([])
def readiness(request):
    """Readiness probe (FR-ADM-1): the database plus every backing dependency.

    The database is required (a failure returns 503); Redis, Kafka and Qdrant
    are reported per-dependency so operators can see degraded infrastructure
    without taking the API out of rotation for, say, a transient Qdrant blip.
    """
    checks = {
        "database": _check_database(),
        "redis": _check_redis(),
        "kafka": _check_kafka(),
        "qdrant": _check_qdrant(),
    }
    db_ok = checks["database"] == "ok"
    degraded = any(v != "ok" for v in checks.values())
    return Response(
        {
            "status": "ready" if db_ok and not degraded else ("degraded" if db_ok else "down"),
            "checks": checks,
        },
        status=200 if db_ok else 503,
    )


def _check_database():
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return "ok"
    except Exception:
        return "unavailable"


def _check_redis():
    try:
        from research.streaming import get_redis

        get_redis().ping()
        return "ok"
    except Exception:
        return "unavailable"


def _check_kafka():
    try:
        from research.messaging import get_producer

        return "ok" if get_producer().bootstrap_connected() else "unavailable"
    except Exception:
        return "unavailable"


def _check_qdrant():
    try:
        with urllib.request.urlopen(f"{settings.QDRANT_URL}/readyz", timeout=1) as resp:
            return "ok" if resp.status == 200 else "unavailable"
    except Exception:
        return "unavailable"
