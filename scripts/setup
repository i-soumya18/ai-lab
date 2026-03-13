#!/usr/bin/env bash
# =============================================================================
# AI Lab — First-time WSL Setup
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ── Check prerequisites ─────────────────────────────────────────────────────
check_command() {
    if ! command -v "$1" &> /dev/null; then
        log_error "$1 is not installed. Please install it first."
        return 1
    fi
    log_info "$1 found: $(command -v "$1")"
}

log_info "=== AI Lab Setup ==="
log_info "Project root: $PROJECT_ROOT"

check_command docker
check_command "docker compose" 2>/dev/null || check_command docker-compose

# ── Create .env from template ────────────────────────────────────────────────
if [ ! -f "$PROJECT_ROOT/.env" ]; then
    log_info "Creating .env from .env.example..."
    cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
    log_info ".env created. Edit it if you need to change defaults."
else
    log_warn ".env already exists, skipping."
fi

# ── Create output directories ───────────────────────────────────────────────
for dir in outputs data templates; do
    mkdir -p "$PROJECT_ROOT/$dir"
done
log_info "Output directories created."

# ── Start Docker if not running ──────────────────────────────────────────────
if ! docker info &> /dev/null; then
    log_warn "Docker daemon not running. Attempting to start..."
    sudo service docker start || {
        log_error "Failed to start Docker. Please start it manually."
        exit 1
    }
    sleep 3
fi
log_info "Docker daemon is running."

# ── Build containers ─────────────────────────────────────────────────────────
log_info "Building Docker containers..."
cd "$PROJECT_ROOT"
docker compose build

# ── Start infrastructure services first ──────────────────────────────────────
log_info "Starting infrastructure services..."
docker compose up -d ollama postgres redis chromadb

# ── Wait for services to be healthy ──────────────────────────────────────────
log_info "Waiting for services to be healthy..."
TIMEOUT=120
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT ]; do
    HEALTHY=$(docker compose ps --format json 2>/dev/null | grep -c '"healthy"' || true)
    TOTAL=4
    if [ "$HEALTHY" -ge "$TOTAL" ]; then
        break
    fi
    sleep 5
    ELAPSED=$((ELAPSED + 5))
    log_info "  Waiting... ($ELAPSED/${TIMEOUT}s, $HEALTHY/$TOTAL healthy)"
done

if [ $ELAPSED -ge $TIMEOUT ]; then
    log_error "Timeout waiting for services. Check: docker compose ps"
    exit 1
fi

# ── Pull Ollama models ───────────────────────────────────────────────────────
log_info "Pulling Ollama models..."
bash "$SCRIPT_DIR/pull-models.sh"

# ── Start remaining services ─────────────────────────────────────────────────
log_info "Starting all services..."
docker compose up -d

log_info "=== Setup Complete ==="
log_info "API:      http://localhost:8000"
log_info "Frontend: http://localhost:3000"
log_info ""
log_info "Run 'make logs' to see service logs."
