# DeepResearch — Agentic AI Research Assistant (RAG + Tool Use)

An end-to-end, production-style **GenAI / Agentic / RAG** application.

Give it a question → an autonomous agent **plans** sub-questions, **searches** the web
and your uploaded documents, **verifies** claims against sources, and writes a
**cited research report** — streaming each step to you live.

Built to demonstrate real production engineering, not just an API call:
microservices, async messaging, containerization, orchestration, CI/CD, and evals.

---

## Architecture

```
React (Vite)  ──HTTP / SSE──►  Django + DRF ──produce──►  Kafka  ──consume──►  Agent Worker(s)
     ▲                              │   ▲                   topics                   │
     │                           MySQL    │             (jobs, events)      Claude API + Web Search
     └──── live progress ◄── Redis ◄──────┴───────── progress events ◄───────────────┘
                                                                       Qdrant (RAG vector store)
```

| Layer            | Tech                                  | Responsibility                                        |
|------------------|---------------------------------------|-------------------------------------------------------|
| Frontend         | React + Vite                          | Chat UI, live agent-step streaming, report viewer     |
| API              | Django + Django REST Framework, JWT   | Auth, users, reports, run history, job dispatch        |
| Messaging        | Apache Kafka                          | Async job queue + progress event stream                |
| Worker           | Python (Kafka consumer)               | The agent loop: plan → search → verify → cite          |
| LLM              | Claude (Anthropic API)                | Reasoning, tool use, synthesis                          |
| RAG store        | Qdrant                                | Vector search over uploaded documents                  |
| Cache / fan-out  | Redis                                 | Caching + SSE/WebSocket progress fan-out               |
| Database         | MySQL 8                               | Source of truth                                        |
| Containerization | Docker / docker-compose               | Local dev, every service containerized                 |
| Orchestration    | Kubernetes                            | Production deploy, independent worker scaling          |
| CI/CD            | GitHub Actions                        | Lint → test → build images → deploy                    |

---

## Repository layout

```
research-agent/
├── backend/          # Django + DRF API (auth, reports, job dispatch)
├── worker/           # Kafka consumer running the agent loop
├── frontend/         # React (Vite) single-page app
├── infra/
│   ├── k8s/          # Kubernetes manifests
│   └── ...           # other infra config
├── .github/
│   └── workflows/    # CI/CD pipelines
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Quick start (local)

```bash
cp .env.example .env          # then add your ANTHROPIC_API_KEY
docker compose up --build     # boots mysql, qdrant, kafka, redis, backend, worker, frontend
```

| Service   | URL                       |
|-----------|---------------------------|
| Frontend  | http://localhost:5173     |
| API       | http://localhost:8000/api |
| Qdrant UI | http://localhost:6333/dashboard |

---

## Build phases

- [x] **Phase 0** — Monorepo skeleton + docker-compose
- [x] **Phase 1** — Django API + JWT auth + MySQL models
- [x] **Phase 2** — Agent worker (Claude tool-use loop)
- [x] **Phase 3** — Kafka wiring + Redis SSE streaming
- [x] **Phase 4** — React UI
- [ ] **Phase 5** — RAG with Qdrant  ← *current*
- [ ] **Phase 6** — Evals + observability
- [ ] **Phase 7** — Dockerfiles → CI/CD → Kubernetes
- [ ] **Phase 8** — Live deploy + polish

---

## Backend API (Phase 1)

The Django + DRF API lives in `backend/`. Run it locally against a MySQL
instance (defaults assume user `root`, database `research`):

```bash
cd backend
python -m venv .venv && source .venv/Scripts/activate   # Windows
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Endpoints are versioned under `/api/v1`:

| Method & Path                     | Auth | Purpose                                  |
|-----------------------------------|------|------------------------------------------|
| `POST /auth/register`             | —    | Create an account                        |
| `POST /auth/token`                | —    | Obtain JWT access + refresh tokens       |
| `POST /auth/token/refresh`        | JWT  | Rotate the access token                  |
| `GET  /auth/me`                   | JWT  | Current user profile                     |
| `POST /runs`                      | JWT  | Submit a question → `QUEUED` run         |
| `GET  /runs`                      | JWT  | List the caller's runs (newest first)    |
| `GET  /runs/{id}`                 | JWT  | Fetch a run and its report               |
| `GET  /runs/{id}/events`          | JWT  | Live progress over SSE (`?token=` for EventSource) |
| `POST /runs/{id}/cancel`          | JWT  | Cancel a `QUEUED`/`RUNNING` run          |
| `POST /documents`                 | JWT  | Upload a document for RAG ingestion      |
| `GET  /documents`                 | JWT  | List the caller's documents              |
| `GET  /health`                    | —    | Liveness/readiness probe                 |

Run the test suite with `python manage.py test`.

---

## Agent worker (Phase 2)

The autonomous research agent lives in `worker/`. It runs a Claude tool-use loop
— **plan** the sub-questions, **search** the web, **verify** claims against
sources, **cite** them — and emits a structured progress event for every step.
Output is a structured report (summary + sections + citations) that maps onto
the `Report`/`Citation` models.

It uses Claude (Opus 4.8) with adaptive thinking and the Anthropic web-search
server tool; research depth (`quick`/`standard`/`deep`) controls the iteration,
search and token/wall-clock budgets.

To develop the agent in isolation (no Kafka/Redis), run one job from the CLI —
progress prints to stderr, the final cited report to stdout:

```bash
cd worker
python -m venv .venv && source .venv/Scripts/activate   # Windows
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...                      # or put it in .env
python -m worker.cli "Compare Kafka and RabbitMQ for an event queue" --depth deep
```

---

## Messaging & live streaming (Phase 3)

Submitting a run publishes a job to the Kafka topic `research.jobs`; the worker
(`python -m worker.main`) consumes it, drives the run through
`QUEUED → RUNNING → (COMPLETED | FAILED | CANCELLED)` (FR-RUN-4), persists the
report and citations, and accounts tokens/cost. A terminally failed run is
routed to `research.jobs.dlq` (FR-RUN-7).

Every agent step is published to a per-run **Redis stream**; the API exposes it
at `GET /runs/{id}/events` as Server-Sent Events (FR-STR-1..4). Redis streams
give ordered delivery, a resumable cursor (reconnect with `Last-Event-ID`), and
history for late subscribers; each run ends with one terminal event. The worker
reuses the backend's Django ORM and the shared `research.messaging` /
`research.streaming` helpers so the schema and event format have a single source
of truth.

---

## Frontend (Phase 4)

A React + Vite single-page app in `frontend/`: email/password auth (JWT with
silent refresh), a question/depth submission form, a run-history list, and a run
view that streams the agent's steps live over SSE and renders the final cited
report. It subscribes to `GET /runs/{id}/events` via `EventSource` (token passed
as a query parameter) and refetches the run for the report on the terminal
event.

```bash
cd frontend
npm install
# API base defaults to http://localhost:8000/api; override with VITE_API_URL
npm run dev          # http://localhost:5173
```

---

## Status

🚧 Phases 0–4 complete — API + JWT auth, the relational data model, the agent
worker (plan → search → verify → cite), async job dispatch with live SSE
streaming, and the React UI are in place. Next up: RAG over uploaded documents
with Qdrant (Phase 5).
