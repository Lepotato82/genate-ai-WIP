-- Knowledge Layer: approved_runs table
-- Run this migration in the Supabase SQL editor before enabling KNOWLEDGE_LAYER_ENABLED=true.

CREATE TABLE IF NOT EXISTS approved_runs (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id             TEXT NOT NULL,
    run_id             TEXT NOT NULL UNIQUE,
    brand_profile      JSONB NOT NULL,
    product_knowledge  JSONB NOT NULL,
    strategy_brief     JSONB NOT NULL,
    approved_copy      TEXT NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_approved_runs_org
    ON approved_runs (org_id);

CREATE INDEX IF NOT EXISTS idx_approved_runs_created
    ON approved_runs (created_at DESC);

-- Row-level security for multi-tenant isolation.
-- The service-role key bypasses RLS; the anon key respects it.
-- Set the current org context via: SET app.current_org_id = '<org_id>';
ALTER TABLE approved_runs ENABLE ROW LEVEL SECURITY;

CREATE POLICY org_isolation ON approved_runs
    USING (org_id = current_setting('app.current_org_id', true));
