-- Step tracking: one row per workflow step per session, pre-populated at session creation
CREATE TABLE session_steps (
    id            UUID PRIMARY KEY,                -- UUIDv7
    session_id    UUID NOT NULL REFERENCES sessions (id) ON DELETE CASCADE,
    step_name     VARCHAR(20) NOT NULL
                  CHECK (step_name IN ('plan', 'test', 'implement', 'review')),
    status        VARCHAR(10) NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'running', 'finished', 'failed')),
    scheduled_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at    TIMESTAMPTZ,
    ended_at      TIMESTAMPTZ,
    error_details TEXT,
    UNIQUE (session_id, step_name)
);

CREATE INDEX idx_session_steps_session_id ON session_steps (session_id);
CREATE INDEX idx_session_steps_status     ON session_steps (status);

-- Enhance context_history with agent name, duration, and step correlation
ALTER TABLE context_history
    ADD COLUMN agent       VARCHAR(20),
    ADD COLUMN duration_ms INTEGER,
    ADD COLUMN step_id     UUID REFERENCES session_steps (id) ON DELETE SET NULL;

CREATE INDEX idx_context_step_id ON context_history (step_id);
