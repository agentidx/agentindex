-- Smedjan Factory Core — schema for autonomous task queue.
-- Applied via:
--   /opt/homebrew/Cellar/postgresql@16/16.11_1/bin/psql \
--     -h 100.119.193.70 -U anstudio -d agentindex \
--     -f ~/agentindex/smedjan/schema.sql
-- Idempotent (IF NOT EXISTS everywhere).

CREATE SCHEMA IF NOT EXISTS smedjan;

-- Enum types ---------------------------------------------------------------
DO $$ BEGIN
    CREATE TYPE smedjan.task_status AS ENUM (
        'pending',          -- created; deps/evidence not yet resolved
        'queued',           -- ready to be claimed (auto-approved or low-risk)
        'needs_approval',   -- waiting for Anders' approval
        'approved',         -- approved; awaiting scheduled_start_at or claim
        'in_progress',      -- claimed by a worker
        'done',             -- complete
        'blocked'           -- blocked; needs intervention
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE smedjan.risk_level AS ENUM ('low', 'medium', 'high');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Task table ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS smedjan.tasks (
    id                   text         PRIMARY KEY,
    title                text         NOT NULL,
    description          text         NOT NULL,
    acceptance_criteria  text         NOT NULL,
    dependencies         text[]       NOT NULL DEFAULT '{}',
    risk_level           smedjan.risk_level NOT NULL DEFAULT 'low',
    whitelisted_files    text[]       NOT NULL DEFAULT '{}',
    status               smedjan.task_status NOT NULL DEFAULT 'pending',
    claimed_by           text,
    claimed_at           timestamptz,
    done_at              timestamptz,
    blocker_reason       text,
    output_paths         text[]       NOT NULL DEFAULT '{}',
    priority             integer      NOT NULL DEFAULT 100,
    created_at           timestamptz  NOT NULL DEFAULT now(),
    updated_at           timestamptz  NOT NULL DEFAULT now(),
    session_group        text,
    scheduled_start_at   timestamptz,
    wait_for_evidence    text,
    is_fallback          boolean      NOT NULL DEFAULT false,
    fallback_category    text,        -- 'F1' | 'F2' | 'F3' | NULL
    evidence             jsonb,       -- parsed from ---TASK_RESULT---
    notes                text,
    approved_by          text,
    approved_at          timestamptz
);

-- risk=high approvals MUST carry scheduled_start_at
ALTER TABLE smedjan.tasks DROP CONSTRAINT IF EXISTS high_risk_needs_start_at;
ALTER TABLE smedjan.tasks ADD CONSTRAINT high_risk_needs_start_at CHECK (
    risk_level <> 'high'
    OR status <> 'approved'
    OR scheduled_start_at IS NOT NULL
);

-- Keep updated_at honest.
CREATE OR REPLACE FUNCTION smedjan._touch_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_tasks_touch ON smedjan.tasks;
CREATE TRIGGER trg_tasks_touch
    BEFORE UPDATE ON smedjan.tasks
    FOR EACH ROW EXECUTE FUNCTION smedjan._touch_updated_at();

-- Indexes ------------------------------------------------------------------
-- Claim-path hot index: the worker's SELECT ... FOR UPDATE SKIP LOCKED.
CREATE INDEX IF NOT EXISTS idx_tasks_claimable
    ON smedjan.tasks (status, priority, created_at)
    WHERE status IN ('queued', 'approved');

CREATE INDEX IF NOT EXISTS idx_tasks_status
    ON smedjan.tasks (status);

CREATE INDEX IF NOT EXISTS idx_tasks_session_group
    ON smedjan.tasks (session_group)
    WHERE session_group IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_tasks_wait_for_evidence
    ON smedjan.tasks (wait_for_evidence)
    WHERE wait_for_evidence IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_tasks_scheduled_start_at
    ON smedjan.tasks (scheduled_start_at)
    WHERE scheduled_start_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_tasks_fallback
    ON smedjan.tasks (fallback_category, priority)
    WHERE is_fallback = true AND status IN ('queued', 'approved');

-- Evidence signals ---------------------------------------------------------
-- Populated by external agents (e.g. L1 observation LaunchAgent). Tasks
-- with wait_for_evidence = <name> stay 'pending' until a row appears here.
CREATE TABLE IF NOT EXISTS smedjan.evidence_signals (
    name          text         PRIMARY KEY,
    available_at  timestamptz  NOT NULL DEFAULT now(),
    payload       jsonb,
    created_by    text
);

CREATE INDEX IF NOT EXISTS idx_evidence_signals_available_at
    ON smedjan.evidence_signals (available_at);

-- Worker heartbeat log -----------------------------------------------------
-- Minimal audit so a dead worker can be detected + restarted without losing
-- the task it was on (claim_at is the source of truth; this is operator UX).
CREATE TABLE IF NOT EXISTS smedjan.worker_heartbeats (
    worker_id     text         PRIMARY KEY,
    last_seen_at  timestamptz  NOT NULL DEFAULT now(),
    current_task  text,
    note          text
);
