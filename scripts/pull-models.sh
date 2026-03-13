#!/usr/bin/env bash
# =============================================================================
# AI Lab — Pull Required Ollama Models
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Source environment variables
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

DEFAULT_MODEL="${DEFAULT_MODEL:-nemotron-3-super:cloud}"

echo "[AI Lab] Pulling Ollama models..."

# Wait for Ollama to be ready
TIMEOUT=60
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT ]; do
    if docker exec ailab-ollama curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; then
        break
    fi
    sleep 3
    ELAPSED=$((ELAPSED + 3))
    echo "  Waiting for Ollama to be ready... ($ELAPSED/${TIMEOUT}s)"
done

if [ $ELAPSED -ge $TIMEOUT ]; then
    echo "[ERROR] Ollama is not responding."
    exit 1
fi

# Pull the default model
echo "[AI Lab] Pulling model: $DEFAULT_MODEL"
docker exec ailab-ollama ollama pull "$DEFAULT_MODEL"

echo "[AI Lab] All models pulled successfully."
