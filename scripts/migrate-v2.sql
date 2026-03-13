-- =============================================================================
-- AI Lab v2 Migration — Goal-Oriented Persistent Assistant
-- Idempotent: safe to run multiple times (all IF NOT EXISTS)
-- Usage: docker exec -i ailab-postgres psql -U ailab -d ailab < scripts/migrate-v2.sql
-- =============================================================================

-- ── Goals ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS goals (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title       TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'pending',
    tasks       JSONB NOT NULL DEFAULT '[]',
    context     JSONB NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_goals_status     ON goals(status);
CREATE INDEX IF NOT EXISTS idx_goals_created_at ON goals(created_at DESC);

-- ── Approval Requests ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS approval_requests (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    goal_id            UUID REFERENCES goals(id) ON DELETE CASCADE,
    task_step          INTEGER,
    action_type        TEXT NOT NULL,
    action_description TEXT NOT NULL,
    action_payload     JSONB NOT NULL DEFAULT '{}',
    status             TEXT NOT NULL DEFAULT 'pending',
    requested_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at        TIMESTAMPTZ,
    resolved_by        TEXT
);

CREATE INDEX IF NOT EXISTS idx_approvals_status  ON approval_requests(status);
CREATE INDEX IF NOT EXISTS idx_approvals_goal_id ON approval_requests(goal_id);

-- ── Activity Log ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS activity_log (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type  TEXT NOT NULL,
    entity_type TEXT,
    entity_id   TEXT,
    description TEXT NOT NULL,
    payload     JSONB NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_activity_event_type ON activity_log(event_type);
CREATE INDEX IF NOT EXISTS idx_activity_entity     ON activity_log(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_activity_created_at ON activity_log(created_at DESC);

-- ── Watched Paths ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS watched_paths (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    path                  TEXT NOT NULL UNIQUE,
    recursive             BOOLEAN NOT NULL DEFAULT TRUE,
    trigger_goal_template TEXT,
    enabled               BOOLEAN NOT NULL DEFAULT TRUE,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

\echo 'AI Lab v2 migration complete.'
