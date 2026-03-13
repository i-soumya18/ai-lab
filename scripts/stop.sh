#!/usr/bin/env bash
# =============================================================================
# AI Lab — Stop All Services
# Usage: ./scripts/stop.sh [--volumes]
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

EXTRA_ARGS=""
for arg in "$@"; do
    case $arg in
        --volumes) EXTRA_ARGS="--volumes" ;;
    esac
done

cd "$PROJECT_ROOT"

echo "[AI Lab] Stopping all services..."
docker compose down $EXTRA_ARGS

echo "[AI Lab] All services stopped."
