-- Coding sessions managed by the Sovereign Brain
CREATE TABLE sessions (
    id          UUID PRIMARY KEY,           -- UUIDv7
    request     TEXT NOT NULL,              -- original user request
    plan        JSONB,                      -- Architect's output
    test_spec   JSONB,                      -- Tester's output
    implementation JSONB,                   -- Dev agent's output
    review      JSONB,                      -- Reviewer's output
    status      VARCHAR(20) NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'testing', 'implementing', 'reviewing', 'approved', 'rejected', 'abandoned')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_sessions_status     ON sessions (status);
CREATE INDEX idx_sessions_created_at ON sessions (created_at DESC);

CREATE TRIGGER trg_sessions_updated_at
    BEFORE UPDATE ON sessions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
