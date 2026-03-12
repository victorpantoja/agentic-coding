ALTER TABLE context_history
    DROP COLUMN IF EXISTS step_id,
    DROP COLUMN IF EXISTS duration_ms,
    DROP COLUMN IF EXISTS agent;

DROP TABLE IF EXISTS session_steps;
