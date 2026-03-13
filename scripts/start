#!/usr/bin/env bash
# =============================================================================
# AI Lab — Start All Services
# Usage: ./scripts/start.sh [--silent]
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SILENT=false

for arg in "$@"; do
    case $arg in
        --silent) SILENT=true ;;
    esac
done

log() {
    if [ "$SILENT" = false ]; then
        echo "$@"
    fi
}

# ── Start Docker if not running ──────────────────────────────────────────────
if ! docker info &> /dev/null; then
    log "[AI Lab] Starting Docker daemon..."
    sudo service docker start 2>/dev/null || true
    sleep 3
    if ! docker info &> /dev/null; then
        log "[AI Lab] ERROR: Docker daemon failed to start."
        exit 1
    fi
fi

# ── Start all services ───────────────────────────────────────────────────────
cd "$PROJECT_ROOT"
docker compose up -d

# ── Wait for health checks ──────────────────────────────────────────────────
log "[AI Lab] Waiting for services to become healthy..."
TIMEOUT=120
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT ]; do
    # Count healthy services
    ALL_HEALTHY=true
    for svc in ollama postgres redis chromadb api frontend; do
        STATUS=$(docker inspect --format='{{.State.Health.Status}}' "ailab-$svc" 2>/dev/null || echo "missing")
        if [ "$STATUS" != "healthy" ]; then
            ALL_HEALTHY=false
            break
        fi
    done

    if [ "$ALL_HEALTHY" = true ]; then
        break
    fi

    sleep 5
    ELAPSED=$((ELAPSED + 5))
done

if [ $ELAPSED -ge $TIMEOUT ]; then
    log "[AI Lab] WARNING: Some services may not be healthy yet."
fi

# ── Print status table ───────────────────────────────────────────────────────
if [ "$SILENT" = false ]; then
    echo ""
    echo "┌─────────────────────────────────────────────────┐"
    echo "│              AI Lab — Service Status             │"
    echo "├──────────────┬──────────────┬───────────────────┤"
    echo "│ Service      │ Status       │ URL               │"
    echo "├──────────────┼──────────────┼───────────────────┤"

    print_svc() {
        local name=$1
        local container=$2
        local url=$3
        STATUS=$(docker inspect --format='{{.State.Health.Status}}' "$container" 2>/dev/null || echo "unknown")
        printf "│ %-12s │ %-12s │ %-17s │\n" "$name" "$STATUS" "$url"
    }

    print_svc "API"       "ailab-api"       "localhost:8000"
    print_svc "Frontend"  "ailab-frontend"  "localhost:3000"
    print_svc "Ollama"    "ailab-ollama"    "internal:11434"
    print_svc "PostgreSQL" "ailab-postgres" "internal:5432"
    print_svc "Redis"     "ailab-redis"     "internal:6379"
    print_svc "ChromaDB"  "ailab-chromadb"  "internal:8000"

    echo "└──────────────┴──────────────┴───────────────────┘"
    echo ""
fi

exit 0
