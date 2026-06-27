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
     │                          Postgres  │             (jobs, events)      Claude API + Web Search
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
| Database         | PostgreSQL                            | Source of truth                                        |
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
docker compose up --build     # boots postgres, qdrant, kafka, redis, backend, worker, frontend
```

| Service   | URL                       |
|-----------|---------------------------|
| Frontend  | http://localhost:5173     |
| API       | http://localhost:8000/api |
| Qdrant UI | http://localhost:6333/dashboard |

---

## Build phases

- [ ] **Phase 0** — Monorepo skeleton + docker-compose  ← *current*
- [ ] **Phase 1** — Django API + JWT auth + Postgres models
- [ ] **Phase 2** — Agent worker (Claude tool-use loop)
- [ ] **Phase 3** — Kafka wiring + Redis SSE streaming
- [ ] **Phase 4** — React UI
- [ ] **Phase 5** — RAG with Qdrant
- [ ] **Phase 6** — Evals + observability
- [ ] **Phase 7** — Dockerfiles → CI/CD → Kubernetes
- [ ] **Phase 8** — Live deploy + polish

---

## Status

🚧 Phase 0 — scaffolding. See checklist above.
