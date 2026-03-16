CREATE TABLE task_history (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id        UUID        NOT NULL REFERENCES sessions (id) ON DELETE CASCADE,
    iteration         INTEGER     NOT NULL,
    reviewer_critique TEXT        NOT NULL DEFAULT '',
    diff              TEXT        NOT NULL DEFAULT '',
    lint_output       JSONB       NOT NULL DEFAULT '{}',
    arch_output       JSONB       NOT NULL DEFAULT '{}',
    is_approved       BOOLEAN     NOT NULL DEFAULT false,
    lessons_learned   TEXT        NOT NULL DEFAULT '',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (session_id, iteration)
);

CREATE INDEX task_history_session_id_idx ON task_history (session_id);
