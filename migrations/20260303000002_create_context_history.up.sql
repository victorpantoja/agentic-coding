-- Historical context for each session event (plan, test, implement, review)
CREATE TABLE context_history (
    id          UUID PRIMARY KEY,           -- UUIDv7
    session_id  UUID NOT NULL REFERENCES sessions (id) ON DELETE CASCADE,
    event_type  VARCHAR(50) NOT NULL
                CHECK (event_type IN ('plan', 'test', 'implement', 'review', 'feedback')),
    data        JSONB NOT NULL DEFAULT '{}',
    summary     TEXT NOT NULL DEFAULT '',  -- human-readable summary for full-text search
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_context_session_id  ON context_history (session_id);
CREATE INDEX idx_context_event_type  ON context_history (event_type);
CREATE INDEX idx_context_created_at  ON context_history (created_at DESC);
-- GIN index for JSONB queries
CREATE INDEX idx_context_data_gin    ON context_history USING GIN (data);
-- Full-text search index on summary
CREATE INDEX idx_context_summary_fts ON context_history USING GIN (to_tsvector('english', summary));
