# DeepResearch — Agentic AI Research Assistant (RAG + Tool Use)

An end-to-end, production-style **GenAI / Agentic / RAG** application.

Give it a question → an autonomous agent **plans** sub-questions, **searches** the web
and your uploaded documents, **verifies** claims against sources, and writes a
**cited research report** — streaming each step to you live.

Built to demonstrate real production engineering, not just an API call:
microservices, async messaging, containerization, orchestration, CI/CD, and evals.

[![CI](https://github.com/Shivamchaubey14/research-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/Shivamchaubey14/research-agent/actions/workflows/ci.yml)

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
- [x] **Phase 5** — RAG with Qdrant
- [x] **Phase 6** — Evals + observability
- [ ] **Phase 7** — Dockerfiles → CI/CD → Kubernetes  ← *current*
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

## RAG ingestion (Phase 5)

Uploading a document (`POST /documents`) persists the file and publishes a
`documents.ingest` job. The worker consumes it (alongside research jobs),
extracts the text (PDF via `pypdf`; TXT/Markdown directly), splits it into
overlapping chunks, embeds them locally with **fastembed** (`bge-small-en-v1.5`,
no embedding API key), and upserts them into a **Qdrant** collection. Each chunk
keeps a `user_id` (so retrieval is scoped to the owner) and a resolvable
`document_id#chunk_index` reference back to its source. The document's status
moves `processing → ready` (or `failed`) with its chunk count (FR-RAG-1,2,5,6).

When a run's user has ingested documents, the agent is given a client-side
`document_search` tool alongside web search: it embeds the query, retrieves the
top-k most relevant chunks from Qdrant (filtered to that user — FR-RAG-3), and
folds them into the evidence as first-class sources. Document-backed claims are
cited with `kind="document"` and the chunk's `doc_ref` (FR-RAG-4, FR-RPT-2).
Runs by users with no documents are unchanged (web only).

---

## Observability (Phase 6)

Both tiers log **structured JSON**, one event per line, correlated by `run_id`
so a single run can be traced across the API and worker (NFR-OBS-1, FR-ADM-2).

Operational endpoints:

| Method & Path                 | Auth  | Purpose                                                   |
|-------------------------------|-------|----------------------------------------------------------|
| `GET /health`                 | —     | Liveness — process up + database reachable               |
| `GET /ready`                  | —     | Readiness — per-dependency check (DB, Redis, Kafka, Qdrant) |
| `GET /admin/metrics`          | staff | Run counts, queue depth, error rate, avg latency, token spend, cost, worker heartbeat |
| `GET /admin/runs?status=`     | staff | Inspect runs across users (defaults to `FAILED`)         |

`/ready` returns 503 only if the database is down; other dependencies are
reported as `degraded` so a transient Qdrant/Kafka blip doesn't pull the API
out of rotation. The worker writes a heartbeat to Redis that `/admin/metrics`
surfaces (FR-ADM-1,3,4, NFR-OBS-2).

---

## Agent evaluation (Phase 6)

Because the agent is probabilistic, quality is measured with a versioned eval
suite rather than fixed assertions (SRS §11.2). It runs the agent over a curated
question set and scores each report with an **LLM-as-judge** on faithfulness,
citation validity, answer relevance and hallucination rate, alongside per-run
cost and latency. The suite mean of each metric is gated against promotion
thresholds and the command exits non-zero on failure, so CI can block a
regressing release.

```bash
cd worker
python -m worker.evals            # prints a scorecard; exit code gates CI
python -m worker.evals out.json   # also writes full results
```

The harness reuses the same `ResearchAgent` the worker runs, so it measures the
real pipeline; it needs `ANTHROPIC_API_KEY` (agent + judge both call Claude).

---

## Containerization (Phase 7)

Every service has a Dockerfile, so `docker compose up --build` boots the whole
stack (infra + API + worker + frontend):

- **backend** — `python:3.13-slim`, installs `requirements.txt`, runs gunicorn
  (compose overrides with `runserver` for dev).
- **worker** — built from the **repo root** (`worker/Dockerfile`) because it
  bundles the backend ORM package it reuses; installs the worker stack
  (Django + driver, Kafka/Redis, `qdrant-client[fastembed]`, `pypdf`).
- **frontend** — `node:20-alpine` running the Vite dev server.

`.dockerignore` files keep build contexts lean (no `.venv`, `node_modules`,
`media`, or `.env`).

---

## CI/CD (Phase 7)

GitHub Actions in `.github/workflows/`:

- **`ci.yml`** (every push/PR to `main`): lints with **ruff**, runs Django's
  system check and the **test suite** against a MySQL service container, builds
  the **frontend**, and builds all three **Docker images** — so a broken
  Dockerfile or failing test blocks the merge (NFR-MNT-1/2).
- **`evals.yml`** (manual + weekly): runs the agent **eval gate**
  (`python -m worker.evals`) using the `ANTHROPIC_API_KEY` repo secret and
  uploads the scorecard. It's separate from `ci.yml` because it calls the Claude
  API (cost + secret); the CLI's exit code gates promotion (§11.2).

Kubernetes manifests (`infra/k8s`) are the remaining slice of this phase.

---

## Status

🚧 Phases 0–6 complete — API + JWT auth, the relational data model, the agent
worker (plan → search → verify → cite), async job dispatch with live SSE
streaming, the React UI, full RAG (document ingestion + agent retrieval),
structured logging + operational endpoints, and a gated agent-eval suite are in
place. Next up: Dockerfiles, CI/CD and Kubernetes (Phase 7).
