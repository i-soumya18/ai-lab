-- =============================================================================
-- AI Lab — PostgreSQL Schema Initialization
-- Executed automatically on first postgres container start
-- =============================================================================

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── Conversations ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS conversations (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       TEXT NOT NULL DEFAULT 'default',
    title         TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_created_at ON conversations(created_at DESC);

-- ── Conversation Messages ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS conversation_messages (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id   UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role              TEXT NOT NULL,
    content           TEXT NOT NULL,
    timestamp         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON conversation_messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON conversation_messages(timestamp DESC);

-- ── Agent Runs ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agent_runs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id       TEXT NOT NULL,
    agent_name    TEXT NOT NULL,
    task_type     TEXT NOT NULL,
    instruction   TEXT NOT NULL,
    output        TEXT,
    success       BOOLEAN NOT NULL,
    model_used    TEXT NOT NULL,
    duration_ms   INTEGER,
    steps_taken   INTEGER,
    error         TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_runs_task_id ON agent_runs(task_id);
CREATE INDEX IF NOT EXISTS idx_agent_runs_agent_name ON agent_runs(agent_name);
CREATE INDEX IF NOT EXISTS idx_agent_runs_created_at ON agent_runs(created_at DESC);

-- ── Automation Jobs ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS automation_jobs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name          TEXT NOT NULL,
    schedule      TEXT NOT NULL,
    task_type     TEXT NOT NULL,
    config        JSONB NOT NULL DEFAULT '{}',
    enabled       BOOLEAN NOT NULL DEFAULT TRUE,
    last_run      TIMESTAMPTZ,
    next_run      TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Goals (v2) ───────────────────────────────────────────────────────────────
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

-- ── Approval Requests (v2) ───────────────────────────────────────────────────
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

-- ── Activity Log (v2) ────────────────────────────────────────────────────────
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

-- ── Watched Paths (v2) ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS watched_paths (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    path                  TEXT NOT NULL UNIQUE,
    recursive             BOOLEAN NOT NULL DEFAULT TRUE,
    trigger_goal_template TEXT,
    enabled               BOOLEAN NOT NULL DEFAULT TRUE,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
