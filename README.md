# Personal AI Lab

A fully local, privacy-first **Personal AI Operating System** that combines chat, RAG, multi-agent orchestration, persistent memory, goal automation, human approvals, kill-switch safety, file watching, and voice interaction in one Dockerized stack.

## Why This Exists
Personal AI Lab is built to run offline-first on your own machine with production-style architecture:

- Local LLM chat with Ollama
- Persistent goal execution across restarts
- Specialist agent system coordinated by an orchestrator
- Safety gates for sensitive actions
- Complete activity trail in PostgreSQL

No cloud API keys are required for core operation.

## Core Capabilities

- `Local LLM Chat Interface`: ChatGPT-style UI powered by Ollama (`nemotron-3-super:cloud`)
- `RAG`: document ingestion + chunking + embeddings + semantic search (ChromaDB)
- `Multi-Agent Orchestration`: orchestrator + specialist agents (research, coding, data, writing, file, goal planner)
- `Persistent Memory`: short-term (Redis), conversation history (PostgreSQL), long-term semantic memory (ChromaDB)
- `Goal-Oriented Automation`: create high-level goals that decompose into executable multi-step tasks
- `Human-in-the-Loop Safety`: approval queue for sensitive actions before execution
- `Kill Switch`: Redis-backed emergency stop for running goals
- `File Watching`: watchdog-based path monitoring that can trigger goals
- `Voice`: TTS endpoint support (Piper); STT currently disabled placeholder
- `Activity Logging`: structured event log in PostgreSQL

## High-Level Architecture

```text
Frontend (Next.js)
  -> FastAPI API Gateway
      -> Orchestrator (LangGraph)
          -> Specialist Agents
      -> Goal Executor (async background engine)
          -> Approval Queue + Kill Switch + Activity Logger

Data Plane:
- Ollama: model inference + embeddings
- PostgreSQL: goals, approvals, activity, conversations, agent runs
- Redis: short-term memory, kill switch, pub/sub
- ChromaDB: RAG + long-term semantic memory
```

## Agent System

- `Orchestrator`: single entry point for agent delegation and workflows
- `Research Agent`: web research + synthesis
- `Coding Agent`: code reasoning, generation, debugging
- `Data Agent`: structured data analysis and insights
- `Writing Agent`: reports, summaries, documentation
- `File Agent`: safe file operations + RAG ingestion
- `Goal Planner Agent`: deterministic decomposition of high-level goals

All agents use structured task/result models and run under timeout/safety constraints.

## Goal Executor (Autonomy Engine)

`goals/goal_executor.py` runs as a FastAPI lifespan background subsystem and provides:

- Step-wise asynchronous execution of goals
- Dependency-aware task progression
- Approval gating before sensitive steps
- Kill-switch checks during execution
- Event publishing for live progress streams
- Persistence and restart-resume behavior

## Safety Model

Sensitive action categories include:

- `file_write`
- `file_delete`
- `shell_exec`
- `web_request`
- `memory_write`
- `goal_start`
- `external_call`

Flow:

1. Agent requests approval
2. Request stored in `approval_requests`
3. Executor waits for approve/deny/timeout
4. Decision logged to `activity_log`

## API Surface (v1)

### Chat + RAG
- `POST /api/v1/chat/message`
- `GET /api/v1/chat/sessions`
- `POST /api/v1/rag/ingest`
- `GET /api/v1/rag/search`

### Agents + Memory
- `GET /api/v1/agents/`
- `POST /api/v1/agents/run`
- `GET /api/v1/memory/recall`

### Goals + Safety + Ops
- `GET /api/v1/goals/`
- `POST /api/v1/goals/`
- `POST /api/v1/goals/{id}/run`
- `POST /api/v1/goals/{id}/pause`
- `POST /api/v1/goals/{id}/cancel`
- `GET /api/v1/goals/{id}/stream`
- `GET /api/v1/approvals/`
- `POST /api/v1/approvals/{id}/approve`
- `POST /api/v1/approvals/{id}/deny`
- `POST /api/v1/system/kill`
- `POST /api/v1/system/resume`
- `GET /api/v1/system/status`
- `GET /api/v1/activity/`
- `GET|POST|DELETE /api/v1/watchers/*`

### Voice
- `POST /api/v1/voice/transcribe` (STT placeholder currently returns not-implemented message)
- `POST /api/v1/voice/speak` (requires Piper runtime/model)

## Tech Stack

- `Backend`: FastAPI + Uvicorn + Python 3.11
- `Frontend`: Next.js 14 + TailwindCSS
- `LLM/Embeddings`: Ollama
- `Vector DB`: ChromaDB
- `Relational DB`: PostgreSQL
- `Cache/Coordination`: Redis
- `Automation`: APScheduler + Celery
- `Containers`: Docker Compose

## Project Layout

```text
agents/       # orchestrator + specialist agents
api/          # FastAPI app + routers
automation/   # scheduler, celery app, file watcher
goals/        # goal models/planner/manager/executor
memory/       # STM/LTM/conversation memory manager
rag/          # ingestion/retrieval/embed pipeline
safety/       # approval queue, kill switch, activity logger
voice/        # STT/TTS/voice handler
frontend/     # Next.js UI
```

## Quick Start

### 1) Prerequisites

- Docker + Docker Compose
- Ollama running locally
- Required models pulled in Ollama (e.g., `nemotron-3-super:cloud`, `nomic-embed-text`)

### 2) Configure

```bash
cp .env.example .env
```

Set your environment values as needed (`OLLAMA_BASE_URL`, DB/Redis/Chroma hostnames, etc.).

### 3) Boot the stack

```bash
docker compose up -d --build
```

### 4) Verify

```bash
curl http://localhost:8000/api/v1/health
```

Open UI at `http://localhost:3000`.

## Developer Workflow

Useful commands (Makefile-backed where available):

```bash
make start
make stop
make logs
make test
```

## Data Stores and Tables

Important persisted entities:

- `goals`
- `approval_requests`
- `activity_log`
- `agent_runs`
- `conversations` and `conversation_messages`
- Chroma collections for RAG and memory

## Current Operational Notes

- STT is intentionally a placeholder until a lightweight local STT backend is integrated
- TTS requires Piper binaries/model to be present in runtime image
- File operations are constrained by safe read/write directory boundaries

## Security and Privacy

- Local-first architecture
- No direct cloud dependency required for core operation
- Sensitive operations routed through approval queue
- Kill switch available for immediate execution halt

## Roadmap Suggestions

- Add end-to-end integration tests for core API paths
- Add watcher event dedup/debounce controls
- Add production-ready local STT implementation
- Add observability dashboards for goals/approvals/events

---

If you are onboarding this codebase, start with `CLAUDE.md` and `AGENTS.md` first; they define system contracts and behavior expectations for every major subsystem.
