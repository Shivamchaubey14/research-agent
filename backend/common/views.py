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
    """Liveness/readiness probe for orchestration (FR-ADM-1).

    Reports overall status plus a per-dependency breakdown. Returns HTTP 200
    when the database is reachable, 503 otherwise.
    """
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
