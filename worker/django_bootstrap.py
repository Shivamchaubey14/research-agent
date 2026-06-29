"""Make the backend's Django models importable from the worker process.

The worker is a separate, independently scaled service (README architecture),
but it reuses the API's ORM models as the single source of truth for the schema
rather than re-declaring the tables. This puts the backend package on the path
and runs ``django.setup()`` so ``research.models`` and the shared
``research.messaging`` / ``research.streaming`` helpers can be imported.
"""
import os
import sys
from pathlib import Path


def setup() -> None:
    backend = os.environ.get("BACKEND_PATH") or str(
        Path(__file__).resolve().parent.parent / "backend"
    )
    if backend not in sys.path:
        sys.path.insert(0, backend)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    import django

    django.setup()
