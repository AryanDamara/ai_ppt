CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Main deck storage
CREATE TABLE IF NOT EXISTS decks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    presentation_id UUID UNIQUE NOT NULL,
    job_id VARCHAR(255) UNIQUE,
    client_request_id VARCHAR(255) UNIQUE,   -- Idempotency key
    generation_status VARCHAR(50) NOT NULL DEFAULT 'draft',
    schema_version VARCHAR(10) NOT NULL DEFAULT '1.0.0',
    deck_json JSONB NOT NULL DEFAULT '{}',
    total_input_tokens INTEGER DEFAULT 0,    -- Cost tracking
    total_output_tokens INTEGER DEFAULT 0,   -- Cost tracking
    estimated_cost_usd DECIMAL(10,6) DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    modified_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_decks_job_id ON decks(job_id);
CREATE INDEX idx_decks_generation_status ON decks(generation_status);
CREATE INDEX idx_decks_presentation_id ON decks(presentation_id);
CREATE INDEX idx_decks_client_request_id ON decks(client_request_id);

-- Semantic cache
CREATE TABLE IF NOT EXISTS prompt_cache (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    prompt_hash VARCHAR(64) NOT NULL UNIQUE,
    prompt_embedding FLOAT8[] NOT NULL,
    result_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    hit_count INTEGER NOT NULL DEFAULT 0,
    expires_at TIMESTAMPTZ NOT NULL,
    invalidated_at TIMESTAMPTZ DEFAULT NULL   -- Manual invalidation support
);

CREATE INDEX idx_cache_prompt_hash ON prompt_cache(prompt_hash);
CREATE INDEX idx_cache_expires_at ON prompt_cache(expires_at);

-- WebSocket event stream (for reconnection catch-up)
CREATE TABLE IF NOT EXISTS ws_events (
    id BIGSERIAL PRIMARY KEY,
    job_id VARCHAR(255) NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    event_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_ws_events_job_id ON ws_events(job_id);
CREATE INDEX idx_ws_events_created_at ON ws_events(created_at);

-- Auto-cleanup ws_events older than 2 hours
CREATE OR REPLACE FUNCTION cleanup_old_ws_events()
RETURNS void AS $$
BEGIN
    DELETE FROM ws_events WHERE created_at < NOW() - INTERVAL '2 hours';
END;
$$ LANGUAGE plpgsql;
