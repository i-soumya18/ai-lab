.PHONY: setup start stop restart logs test ingest pull-models shell-api reset-db build clean

# ── Project paths ─────────────────────────────────────────────────────────────
COMPOSE := docker compose
PROJECT_ROOT := $(shell pwd)

# ── First-time setup ──────────────────────────────────────────────────────────

setup: ## First-time WSL setup — installs Docker, builds containers, pulls models
	@bash "$(PROJECT_ROOT)/scripts/setup.sh"

# ── Service management ────────────────────────────────────────────────────────

start: ## Start all AI Lab services in detached mode
	@bash "$(PROJECT_ROOT)/scripts/start.sh"

stop: ## Stop all services (preserves volumes)
	@bash "$(PROJECT_ROOT)/scripts/stop.sh"

restart: stop start ## Restart all services

build: ## Rebuild all Docker images without cache
	$(COMPOSE) build --no-cache

clean: ## Stop services and remove all volumes (data loss!)
	@echo "⚠️  This will delete all data. Ctrl+C to cancel..."
	@sleep 5
	$(COMPOSE) down --volumes --remove-orphans

# ── Logs ──────────────────────────────────────────────────────────────────────

logs: ## Tail logs for all services
	$(COMPOSE) logs -f

logs-api: ## Tail API service logs
	$(COMPOSE) logs -f api

logs-celery: ## Tail Celery worker logs
	$(COMPOSE) logs -f celery_worker

logs-ollama: ## Tail Ollama logs
	$(COMPOSE) logs -f ollama

# ── Development shells ────────────────────────────────────────────────────────

shell-api: ## Open a shell in the API container
	$(COMPOSE) exec api bash

shell-db: ## Open a PostgreSQL shell
	$(COMPOSE) exec postgres psql -U ailab -d ailab

shell-redis: ## Open a Redis CLI
	$(COMPOSE) exec redis redis-cli

# ── Database ──────────────────────────────────────────────────────────────────

reset-db: ## Drop and recreate all database tables
	$(COMPOSE) exec postgres psql -U ailab -d ailab -f /docker-entrypoint-initdb.d/init.sql
	@echo "✅ Database reset complete"

migrate-v2: ## Apply v2 schema migration (goals, approvals, activity_log, watched_paths)
	docker exec -i ailab-postgres psql -U ailab -d ailab < scripts/migrate-v2.sql
	@echo "✅ v2 migration complete"

# ── Models ────────────────────────────────────────────────────────────────────

pull-models: ## Pull all required Ollama models
	@bash $(PROJECT_ROOT)/scripts/pull-models.sh

list-models: ## List available Ollama models
	$(COMPOSE) exec ollama ollama list

# ── RAG / Ingestion ───────────────────────────────────────────────────────────

ingest: ## Ingest sample documents into the default RAG collection
	@echo "📚 Ingesting CLAUDE.md and AGENTS.md..."
	curl -s -X POST http://localhost:8000/api/v1/rag/ingest \
		-H "Content-Type: application/json" \
		-d '{"source_type": "file", "path": "/app/api/CLAUDE.md", "collection": "project-docs"}' | jq .
	@echo "✅ Ingestion complete"

# ── Tests ─────────────────────────────────────────────────────────────────────

test: ## Run all backend tests
	$(COMPOSE) exec api pytest tests/ -v --tb=short

test-coverage: ## Run tests with coverage report
	$(COMPOSE) exec api pytest tests/ --cov=. --cov-report=term-missing -v

# ── Health check ──────────────────────────────────────────────────────────────

health: ## Check health of all services
	@echo "🔍 API health:"
	@curl -s http://localhost:8000/api/v1/health | jq . || echo "❌ API unreachable"
	@echo "🔍 Ollama:"
	@curl -s http://localhost:11434/api/tags | jq '.models | length' | xargs echo "  Models available:" || echo "❌ Ollama unreachable"
	@echo "🔍 Frontend:"
	@curl -sf http://localhost:3000 -o /dev/null && echo "  ✅ Online" || echo "  ❌ Unreachable"

# ── Help ──────────────────────────────────────────────────────────────────────

help: ## Show this help message
	@echo ""
	@echo "Personal AI Lab — Make targets"
	@echo "================================"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""

.DEFAULT_GOAL := help
