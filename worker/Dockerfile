# Agent worker tier. Build context is the repo ROOT (not ./worker), because the
# worker reuses the backend's Django ORM models — both packages ship in the image.
#   docker build -f worker/Dockerfile .
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    BACKEND_PATH=/app/backend \
    DJANGO_SETTINGS_MODULE=config.settings

WORKDIR /app

# Deps first for layer caching. The worker stack includes Django + driver (for
# the shared ORM), Kafka/Redis, and qdrant-client[fastembed] + pypdf for RAG.
COPY worker/requirements.txt ./worker/requirements.txt
RUN pip install --no-cache-dir -r worker/requirements.txt

COPY backend ./backend
COPY worker ./worker

CMD ["python", "-m", "worker.main"]
