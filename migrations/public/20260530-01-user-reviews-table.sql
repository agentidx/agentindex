-- 2026-05-30 Stop the per-worker-boot CREATE TABLE retry storm.
-- Context: R-SW phase — agentindex/review_pages.py:_ensure_reviews_table()
-- was called at module-load time from discovery.py:mount_review_pages(),
-- meaning every uvicorn worker boot ran this DDL. When Nbg PG was
-- saturated by the unindexed software_registry scan (separate fix), the
-- DDL timed out, worker died, uvicorn restarted, restart-loop amplified
-- the saturation. Moving the DDL here so worker boot becomes pure-read.
-- Idempotent: yes (IF NOT EXISTS).

BEGIN;

CREATE TABLE IF NOT EXISTS public.user_reviews (
    id            SERIAL PRIMARY KEY,
    agent_name    text NOT NULL,
    rating        integer NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment       text,
    reviewer_name text DEFAULT 'Anonymous',
    ip_hash       text,
    created_at    timestamp NOT NULL DEFAULT now(),
    is_editorial  boolean DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_user_reviews_agent
    ON public.user_reviews (agent_name);

COMMIT;


-- DOWN (manual; for reference)
-- DROP TABLE IF EXISTS public.user_reviews;
