# CLAUDE.md — Personal AI Laboratory

> This file is the primary instruction set for Claude Code when working on the **Personal AI Lab** project.
> Read this entire file before writing any code or making any decisions.

---

## PROJECT OVERVIEW

This project is a **fully local, privacy-first Personal AI Operating System** that runs on Ubuntu WSL.
It gives the user a personal ChatGPT-style interface backed by local Ollama LLMs, a RAG knowledge base,
a multi-agent orchestration system, persistent memory, voice interaction, and automation — all running
in Docker with zero cloud dependencies.

**North Star:** Every feature must work 100% offline. No API keys. No telemetry. No data leaves the machine.

### Goal-Oriented Persistent Assistant (v2 Extension)

The system extends beyond single-prompt responses into a **persistent goal-oriented assistant** that:

- Accepts high-level **Goals** (e.g., "Monitor my research folder and summarize new papers weekly")
- Uses an LLM to **decompose goals** into ordered multi-step agent tasks automatically
- **Executes tasks persistently** across sessions — goals survive container restarts
- **Pauses for human approval** before any sensitive action (file write, shell exec, web request)
- **Logs every event** to a structured activity log (agent runs, approvals, file operations)
- Has a **kill switch** (Redis-backed) to instantly halt all running goals at any time
- **Watches file system paths** and triggers goal tasks when files are created or modified

---

## TECH STACK (NON-NEGOTIABLE)

| Layer              | Technology                                      |
|--------------------|-------------------------------------------------|
| LLM inference      | Ollama (nemotron-3-super:cloud)   |
| Backend API        | Python 3.11 + FastAPI + uvicorn                 |
| Agent framework    | LangGraph (primary), CrewAI (team workflows)    |
| Vector DB          | ChromaDB (persistent mode)                      |
| Embeddings         | Ollama /api/embed (nomic-embed-text)             |
| Relational DB      | PostgreSQL 15                                   |
| Cache / STM        | Redis 7                                         |
| Task queue         | Celery + Redis broker                           |
| Speech-to-text     | TBD (lightweight STT, currently disabled)        |
| Text-to-speech     | Piper TTS                                       |
| Frontend           | Next.js 14 (App Router) + TailwindCSS           |
| Containerization   | Docker + Docker Compose                         |
| Dev environment    | Ubuntu  + VS Code                           |

**Never substitute cloud APIs for any of the above.**
If a library has both local and cloud modes, always configure local mode explicitly.

---

## CANONICAL PROJECT STRUCTURE

Always create files in this exact layout. Never deviate.

```
/ai-lab/
├── CLAUDE.md                    ← this file
├── AGENTS.md                    ← agent roles and task delegation rules
├── docker-compose.yml           ← full service stack
├── .env.example                 ← environment variable template (no secrets)
├── Makefile                     ← developer shortcuts
├── scripts/
│   ├── setup.sh                 ← first-time WSL setup
│   ├── start.sh                 ← start all services
│   ├── stop.sh                  ← stop all services
│   └── pull-models.sh           ← pull required Ollama models
│
├── api/                         ← FastAPI gateway (main entry point)
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py                  ← app factory, router registration
│   ├── config.py                ← settings via pydantic-settings
│   ├── dependencies.py          ← shared FastAPI dependencies
│   └── routers/
│       ├── chat.py              ← /chat endpoints
│       ├── rag.py               ← /rag endpoints
│       ├── agents.py            ← /agents endpoints
│       ├── memory.py            ← /memory endpoints
│       ├── automation.py        ← /automation endpoints
│       └── voice.py             ← /voice endpoints
│
├── agents/                      ← all agent logic
│   ├── __init__.py
│   ├── orchestrator.py          ← manager agent + task routing
│   ├── base_agent.py            ← abstract base class for all agents
│   ├── research_agent.py
│   ├── coding_agent.py
│   ├── data_agent.py
│   ├── writing_agent.py
│   ├── goal_planner_agent.py    ← decomposes goals into task steps
│   ├── file_agent.py            ← file operations + RAG ingestion
│   └── tools/                   ← tools available to agents
│       ├── web_search.py        ← local web scraping (no external APIs)
│       ├── file_tools.py
│       ├── code_tools.py
│       └── memory_tools.py
│
├── goals/                       ← goal management system
│   ├── __init__.py
│   ├── models.py                ← Goal, GoalTask, GoalStatus Pydantic models
│   ├── goal_manager.py          ← CRUD + PostgreSQL persistence
│   ├── goal_planner.py          ← LLM-powered goal decomposition
│   └── goal_executor.py         ← persistent asyncio execution engine
│
├── safety/                      ← human-in-the-loop safety layer
│   ├── __init__.py
│   ├── kill_switch.py           ← Redis-backed kill switch
│   ├── approval_queue.py        ← request/await/resolve approvals
│   └── activity_logger.py       ← structured event log to PostgreSQL
│
├── rag/                         ← retrieval-augmented generation pipeline
│   ├── __init__.py
│   ├── ingestion.py             ← document loading + chunking
│   ├── embedder.py              ← embedding wrapper
│   ├── retriever.py             ← semantic search
│   ├── pipeline.py              ← end-to-end RAG chain
│   └── loaders/
│       ├── pdf_loader.py
│       ├── markdown_loader.py
│       ├── git_loader.py
│       └── notion_loader.py
│
├── memory/                      ← memory management
│   ├── __init__.py
│   ├── short_term.py            ← Redis-backed session memory
│   ├── long_term.py             ← vector DB long-term memory
│   ├── conversation_store.py    ← PostgreSQL conversation history
│   └── memory_manager.py       ← unified interface to all memory layers
│
├── models/                      ← Ollama model management
│   ├── __init__.py
│   ├── router.py                ← selects right model per task type
│   └── ollama_client.py         ← async Ollama API wrapper
│
├── voice/                       ← voice pipeline (STT disabled, TTS ready)
│   ├── __init__.py
│   ├── stt.py                   ← Speech-to-text (stub, TODO: implement lightweight STT)
│   ├── tts.py                   ← Piper TTS
│   └── voice_handler.py         ← full voice loop
│
├── automation/                  ← task scheduling
│   ├── __init__.py
│   ├── scheduler.py             ← APScheduler setup
│   ├── celery_app.py            ← Celery config
│   ├── file_watcher.py          ← watchdog-based file system watcher
│   └── tasks/
│       ├── daily_summary.py
│       ├── news_collector.py
│       └── monitor.py
│
└── frontend/                    ← Next.js chat UI
    ├── Dockerfile
    ├── package.json
    ├── next.config.js
    └── src/
        ├── app/
        │   ├── page.tsx         ← main chat page
        │   ├── layout.tsx
        │   └── api/             ← Next.js API routes (proxy to FastAPI)
        ├── components/
        │   ├── ChatWindow.tsx
        │   ├── MessageBubble.tsx
        │   ├── SidePanel.tsx    ← knowledge base + agents panel
        │   └── VoiceButton.tsx
        └── lib/
            ├── api.ts           ← FastAPI client
            └── types.ts
```

---

## CODING STANDARDS

### Python

- Python 3.11+, strict typing everywhere (`from __future__ import annotations`)
- Use `pydantic v2` for all data models and config
- Use `async/await` throughout — all I/O must be non-blocking
- Use `httpx.AsyncClient` for any HTTP calls (never `requests`)
- All FastAPI routes must have response models defined
- Log using `structlog`, not `print()` or `logging` directly
- Environment variables via `pydantic-settings` in `config.py`
- Raise specific exceptions, never catch bare `Exception` silently
- Every public function must have a docstring and type hints
- Tests go in `tests/` mirroring the source structure

### TypeScript / Next.js

- Use Next.js App Router (not Pages Router)
- All components are functional with hooks
- Use `zod` for API response validation on the frontend
- Tailwind utility classes only — no inline styles
- Use `react-query` (TanStack Query) for all data fetching
- Streaming responses via `fetch` with `ReadableStream`

### Docker

- Every service has its own `Dockerfile` with multi-stage builds where applicable
- Never run containers as root — use a non-root user
- Pin all base image versions (e.g., `python:3.11-slim`)
- Use `.dockerignore` in every service directory
- Health checks must be defined for every service

---

## ENVIRONMENT VARIABLES

All config must flow through environment variables. Never hardcode:
- ports
- hostnames
- model names
- database URLs
- paths

Define all vars in `.env.example` with comments. Load via `config.py`:

```python
# api/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    ollama_base_url: str = "http://ollama:11434"
    chroma_host: str = "chromadb"
    chroma_port: int = 8000
    redis_url: str = "redis://redis:6379/0"
    postgres_url: str = "postgresql+asyncpg://ailab:ailab@postgres:5432/ailab"
    default_model: str = "nemotron-3-super:cloud"
    coder_model: str = "nemotron-3-super:cloud"
    embedding_model: str = "nomic-embed-text"  # Ollama embedding model (via /api/embed)

    class Config:
        env_file = ".env"
```

---

## SERVICE COMMUNICATION

All inter-service communication is **internal Docker network only**:

```
Service Name   → Internal Host    → Port
─────────────────────────────────────────
FastAPI API    → api              → 8000
Ollama         → ollama           → 11434
ChromaDB       → chromadb         → 8000
PostgreSQL     → postgres         → 5432
Redis          → redis            → 6379
Frontend       → frontend         → 3000
Celery Worker  → celery_worker    → (no port)
```

The frontend ONLY talks to FastAPI. It never calls Ollama or ChromaDB directly.

---

## OLLAMA MODEL ROUTING RULES

The model router in `models/router.py` must select models based on task type:

| Task Type          | Model             | Reason                        |
|--------------------|-------------------|-------------------------------|
| General chat       | For now use nemotron-3-super:cloud only as by default later we should abale to config other models            | Best general reasoning        |
| Code generation    | For now use nemotron-3-super:cloud only as by default later we should abale to config other models     | Specialized coding model      |
| Code explanation   | For now use nemotron-3-super:cloud only as by default later we should abale to config other models     | Specialized coding model      |
| Fast/short tasks   | For now use nemotron-3-super:cloud only as by default later we should abale to config other models              | Lightweight, fast             |
| Research writing   | For now use nemotron-3-super:cloud only as by default later we should abale to config other models           | Strong at long-form writing   |
| Embeddings         | nomic-embed-text (via Ollama /api/embed) | Lightweight, no-local-model|

Model selection can be overridden by the user via `model` field in any request body.

---

## RAG PIPELINE RULES

1. **Chunking:** Use `RecursiveCharacterTextSplitter` with `chunk_size=512`, `overlap=64`
2. **Embeddings:** Use `nomic-embed-text` via Ollama's `/api/embed` endpoint — no local embedding models
3. **Retrieval:** Retrieve top-5 chunks by default, configurable per request
4. **Context injection:** Inject retrieved context using a system prompt template:
   ```
   You are a helpful assistant. Use the following context to answer the question.
   If the context doesn't help, say so clearly.

   Context:
   {context}

   Question: {question}
   ```
5. **Collections:** Each document namespace (e.g., "personal-notes", "codebase", "research") gets its own ChromaDB collection

---

## MEMORY ARCHITECTURE

The memory manager must transparently handle three layers:

```
Request
  │
  ▼
memory_manager.get_context(session_id, user_id, query)
  │
  ├─ 1. Short-term (Redis)
  │     └─ Last N messages in current session (TTL: 2 hours)
  │
  ├─ 2. Conversation history (PostgreSQL)
  │     └─ All past conversations, searchable by user + date
  │
  └─ 3. Long-term semantic memory (ChromaDB collection: "memory")
        └─ Summarized facts about user preferences, projects, decisions
```

When saving to long-term memory, **summarize** the conversation first using the LLM, then embed and store the summary — never store raw messages in long-term vector memory.

---

## AGENT ORCHESTRATION RULES

See `AGENTS.md` for full agent specifications.

Key orchestration principles:
1. The **Orchestrator** always decides which agent handles a task — never route directly from the API
2. Agents must emit **structured output** (`AgentResult` Pydantic model) — never raw strings
3. All agent runs must be logged to PostgreSQL with: `agent_name`, `input`, `output`, `duration_ms`, `model_used`
4. Agents must have **timeouts** — no agent run should block for more than 120 seconds
5. Multi-agent workflows use **LangGraph StateGraph** — define state schema explicitly

---

## API DESIGN RULES

All FastAPI endpoints must follow these conventions:

```
GET    /api/v1/chat/sessions              → list sessions
POST   /api/v1/chat/message               → send message (streaming)
GET    /api/v1/rag/search?q=...           → semantic search
POST   /api/v1/rag/ingest                 → upload + ingest document
GET    /api/v1/agents/                    → list available agents
POST   /api/v1/agents/run                 → run an agent task
GET    /api/v1/memory/recall?q=...        → search memory
POST   /api/v1/automation/schedule        → create scheduled task
POST   /api/v1/voice/transcribe           → audio → text
POST   /api/v1/voice/speak               → text → audio

# Goal-Oriented OS endpoints (v2)
GET    /api/v1/goals/                     → list goals (filter by status)
POST   /api/v1/goals/                     → create goal + auto-plan via LLM
GET    /api/v1/goals/{id}                 → goal detail with task steps
POST   /api/v1/goals/{id}/run             → start or resume goal execution
POST   /api/v1/goals/{id}/pause           → pause goal
POST   /api/v1/goals/{id}/cancel          → cancel goal
GET    /api/v1/goals/{id}/stream          → SSE stream of goal progress
GET    /api/v1/approvals/                 → list pending approval requests
POST   /api/v1/approvals/{id}/approve     → approve a sensitive action
POST   /api/v1/approvals/{id}/deny        → deny a sensitive action
POST   /api/v1/system/kill                → activate kill switch (halt all goals)
POST   /api/v1/system/resume              → deactivate kill switch
GET    /api/v1/system/status              → kill switch + running + pending approvals
GET    /api/v1/activity/                  → paginated activity log
GET    /api/v1/watchers/                  → list watched paths
POST   /api/v1/watchers/                  → add a watched path
DELETE /api/v1/watchers/{id}              → remove a watched path
```

- Always version routes under `/api/v1/`
- All endpoints return `{"data": ..., "error": null}` or `{"data": null, "error": "message"}`
- Streaming endpoints use `StreamingResponse` with `text/event-stream`
- File uploads use `UploadFile` — validate file type and size (max 50MB)

---

## AUTO-START ON WSL BOOT

The `scripts/start.sh` must:
1. Check if Docker daemon is running, start it if not
2. Run `docker compose up -d` from the project root
3. Wait for health checks to pass on all services
4. Print a status summary table to the terminal

Add to `~/.bashrc` or `~/.profile`:
```bash
# Auto-start AI Lab
if [ -f "$HOME/ai-lab/scripts/start.sh" ]; then
    bash "$HOME/ai-lab/scripts/start.sh" --silent
fi
```

---

## BUILD ORDER

When implementing features, always follow this order to respect dependencies:

```
Phase 1 — Infrastructure
  1. docker-compose.yml (all services defined)
  2. scripts/setup.sh
  3. api/config.py + api/main.py skeleton
  4. models/ollama_client.py

Phase 2 — Core Features
  5. memory/ (all three layers)
  6. rag/ (ingestion + retrieval)
  7. api/routers/chat.py (streaming chat)
  8. api/routers/rag.py

Phase 3 — Agents
  9.  agents/base_agent.py
  10. agents/orchestrator.py
  11. agents/research_agent.py, coding_agent.py, data_agent.py, writing_agent.py
  12. api/routers/agents.py

Phase 4 — Automation + Voice
  13. automation/ (scheduler + Celery)
  14. voice/ (STT + TTS)
  15. api/routers/automation.py + voice.py

Phase 5 — Frontend
  16. frontend/ (Next.js chat UI)
  17. Streaming chat integration
  18. Document upload UI
  19. Agent panel UI

Phase 6 — Polish
  20. WSL auto-start scripts
  21. Makefile shortcuts
  22. README.md

Phase 7 — Goal-Oriented OS (v2)
  23. safety/ (kill_switch, approval_queue, activity_logger)
  24. goals/ (models, goal_manager, goal_planner, goal_executor)
  25. agents/goal_planner_agent.py + agents/file_agent.py
  26. automation/file_watcher.py
  27. api/routers/{goals, approvals, system, activity, watchers}.py
  28. scripts/migrate-v2.sql

Phase 8 — Frontend v2
  29. frontend/src/components/{GoalPanel, GoalDetail, ApprovalModal}.tsx
  30. frontend/src/components/{ActivityLog, KillSwitch, WatcherPanel}.tsx
  31. Update SidePanel.tsx (new tabs), page.tsx (KillSwitch + ApprovalModal)
```

---

## WHAT NOT TO DO

- ❌ Never use OpenAI, Anthropic, Cohere, or any cloud LLM API
- ❌ Never use `langchain` hub or any online chain pulling
- ❌ Never store secrets in code or docker-compose.yml
- ❌ Never use SQLite in production paths — use PostgreSQL
- ❌ Never block the event loop with synchronous I/O
- ❌ Never skip error handling in agent code — agents can and will fail
- ❌ Never hardcode model names outside of `config.py`
- ❌ Never expose PostgreSQL, Redis, or ChromaDB ports outside Docker network
- ❌ Never use `latest` tags in Docker base images

---

## TESTING STRATEGY

- Use `pytest` + `pytest-asyncio` for all backend tests
- Mock Ollama responses in unit tests using `httpx` transport mocking
- Integration tests require Docker Compose to be running
- Target: >80% coverage on `api/`, `agents/`, `rag/`, `memory/`
- Run tests: `make test`

---

## WHEN CLAUDE CODE IS UNSURE

If requirements are ambiguous:
1. Default to the **most local, most private** solution
2. Default to **async** over sync
3. Default to **explicit config** over magic/convention
4. Ask in a comment: `# TODO(clarify): [question]` — never silently guess

---

## QUICK REFERENCE COMMANDS

```bash
make setup        # First-time WSL setup
make start        # Start all Docker services
make stop         # Stop all services
make logs         # Tail all service logs
make test         # Run all tests
make ingest       # Ingest sample documents into RAG
make pull-models  # Pull all required Ollama models
make shell-api    # Open shell in API container
make reset-db     # Drop and recreate all databases
```
