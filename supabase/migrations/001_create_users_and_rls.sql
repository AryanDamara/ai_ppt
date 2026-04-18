-- Phase 5: Supabase RLS Migration
-- Apply: supabase db push or run manually in SQL editor
-- Row-Level Security ensures tenants only see their own data.

-- ────────────────────────────────────────────────────────────────────────────
-- User profiles (extends Supabase auth.users)
-- ────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS user_profiles (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    auth_user_id    UUID NOT NULL UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,
    email           TEXT NOT NULL,
    display_name    TEXT NOT NULL DEFAULT '',
    plan            TEXT NOT NULL DEFAULT 'free'
                    CHECK (plan IN ('free', 'pro', 'enterprise')),
    tenant_id       UUID NOT NULL DEFAULT gen_random_uuid(),
    role            TEXT NOT NULL DEFAULT 'user'
                    CHECK (role IN ('user', 'admin')),
    consent_level   TEXT NOT NULL DEFAULT 'basic'
                    CHECK (consent_level IN ('none', 'basic', 'full')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "users_own_profile"
    ON user_profiles
    FOR ALL
    USING (auth_user_id = auth.uid());


-- ────────────────────────────────────────────────────────────────────────────
-- Decks (presentations) — with RLS by tenant
-- ────────────────────────────────────────────────────────────────────────────

-- Add tenant scoping columns to existing decks table if missing
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'decks' AND column_name = 'tenant_id'
    ) THEN
        ALTER TABLE decks ADD COLUMN tenant_id UUID;
        ALTER TABLE decks ADD COLUMN user_id UUID REFERENCES auth.users(id);
    END IF;
END $$;

ALTER TABLE decks ENABLE ROW LEVEL SECURITY;

CREATE POLICY "decks_tenant_isolation"
    ON decks
    FOR ALL
    USING (
        tenant_id = (
            SELECT tenant_id FROM user_profiles
            WHERE auth_user_id = auth.uid()
            LIMIT 1
        )
    );


-- ────────────────────────────────────────────────────────────────────────────
-- Documents (uploaded files) — with RLS by tenant
-- ────────────────────────────────────────────────────────────────────────────

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'documents' AND column_name = 'tenant_id'
    ) THEN
        ALTER TABLE documents ADD COLUMN tenant_id UUID;
        ALTER TABLE documents ADD COLUMN user_id UUID REFERENCES auth.users(id);
    END IF;
END $$;

ALTER TABLE documents ENABLE ROW LEVEL SECURITY;

CREATE POLICY "documents_tenant_isolation"
    ON documents
    FOR ALL
    USING (
        tenant_id = (
            SELECT tenant_id FROM user_profiles
            WHERE auth_user_id = auth.uid()
            LIMIT 1
        )
    );


-- ────────────────────────────────────────────────────────────────────────────
-- Feedback table (thumbs up/down, edits)
-- ────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS feedback (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         TEXT NOT NULL,
    tenant_id       TEXT NOT NULL,
    deck_id         TEXT NOT NULL,
    slide_id        TEXT NOT NULL,
    feedback_type   TEXT NOT NULL CHECK (feedback_type IN ('thumbs_up', 'thumbs_down', 'edit')),
    edit_delta      JSONB,
    original_value  TEXT,
    new_value       TEXT,
    trace_id        TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_feedback_deck ON feedback(deck_id);
CREATE INDEX IF NOT EXISTS idx_feedback_tenant ON feedback(tenant_id);
CREATE INDEX IF NOT EXISTS idx_feedback_type ON feedback(feedback_type);

ALTER TABLE feedback ENABLE ROW LEVEL SECURITY;

CREATE POLICY "feedback_own_records"
    ON feedback
    FOR ALL
    USING (user_id = auth.uid()::text);


-- ────────────────────────────────────────────────────────────────────────────
-- Cost tracking table (daily aggregations)
-- ────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS cost_records (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    model           TEXT NOT NULL,
    step            TEXT NOT NULL,
    input_tokens    INTEGER NOT NULL DEFAULT 0,
    output_tokens   INTEGER NOT NULL DEFAULT 0,
    cost_usd        DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    job_id          TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cost_tenant_date ON cost_records(tenant_id, created_at);

ALTER TABLE cost_records ENABLE ROW LEVEL SECURITY;

CREATE POLICY "cost_records_own_tenant"
    ON cost_records
    FOR SELECT
    USING (
        tenant_id IN (
            SELECT tenant_id::text FROM user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );


-- ────────────────────────────────────────────────────────────────────────────
-- Auto-create user profile on signup trigger
-- ────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    INSERT INTO user_profiles (auth_user_id, email, display_name, plan, tenant_id, role)
    VALUES (
        NEW.id,
        NEW.email,
        COALESCE(NEW.raw_user_meta_data->>'display_name', split_part(NEW.email, '@', 1)),
        COALESCE(NEW.raw_user_meta_data->>'plan', 'free'),
        COALESCE(
            (NEW.raw_user_meta_data->>'tenant_id')::uuid,
            gen_random_uuid()
        ),
        COALESCE(NEW.raw_user_meta_data->>'role', 'user')
    );
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW
    EXECUTE FUNCTION handle_new_user();
