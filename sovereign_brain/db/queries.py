"""Raw asyncpg query helpers for sessions and context history."""

from __future__ import annotations

import json

import asyncpg

# ── Sessions ─────────────────────────────────────────────────────────────────

async def create_session(
    conn: asyncpg.Connection,
    session_id: str,
    request: str,
) -> None:
    await conn.execute(
        """
        INSERT INTO sessions (id, request, status)
        VALUES ($1::uuid, $2, 'active')
        """,
        session_id,
        request,
    )


async def update_session_plan(
    conn: asyncpg.Connection,
    session_id: str,
    plan: dict,
) -> None:
    await conn.execute(
        """
        UPDATE sessions
        SET plan = $2::jsonb, updated_at = now()
        WHERE id = $1::uuid
        """,
        session_id,
        json.dumps(plan),
    )


async def update_session_test_spec(
    conn: asyncpg.Connection,
    session_id: str,
    test_spec: dict,
) -> None:
    await conn.execute(
        """
        UPDATE sessions
        SET test_spec = $2::jsonb, updated_at = now()
        WHERE id = $1::uuid
        """,
        session_id,
        json.dumps(test_spec),
    )


async def update_session_implementation(
    conn: asyncpg.Connection,
    session_id: str,
    implementation: dict,
) -> None:
    await conn.execute(
        """
        UPDATE sessions
        SET implementation = $2::jsonb, updated_at = now()
        WHERE id = $1::uuid
        """,
        session_id,
        json.dumps(implementation),
    )


async def update_session_review(
    conn: asyncpg.Connection,
    session_id: str,
    review: dict,
    status: str,
) -> None:
    await conn.execute(
        """
        UPDATE sessions
        SET review = $2::jsonb, status = $3, updated_at = now()
        WHERE id = $1::uuid
        """,
        session_id,
        json.dumps(review),
        status,
    )


async def get_session(
    conn: asyncpg.Connection,
    session_id: str,
) -> dict | None:
    row = await conn.fetchrow(
        "SELECT * FROM sessions WHERE id = $1::uuid",
        session_id,
    )
    if row is None:
        return None
    return dict(row)


async def list_sessions(
    conn: asyncpg.Connection,
    limit: int = 20,
) -> list[dict]:
    rows = await conn.fetch(
        "SELECT id, request, status, created_at FROM sessions ORDER BY created_at DESC LIMIT $1",
        limit,
    )
    return [dict(r) for r in rows]


# ── Context history ───────────────────────────────────────────────────────────

async def append_context(
    conn: asyncpg.Connection,
    context_id: str,
    session_id: str,
    event_type: str,
    data: dict,
    summary: str = "",
    agent: str | None = None,
    duration_ms: int | None = None,
    step_id: str | None = None,
) -> None:
    await conn.execute(
        """
        INSERT INTO context_history
            (id, session_id, event_type, data, summary, agent, duration_ms, step_id)
        VALUES ($1::uuid, $2::uuid, $3, $4::jsonb, $5, $6, $7, $8::uuid)
        """,
        context_id,
        session_id,
        event_type,
        json.dumps(data),
        summary,
        agent,
        duration_ms,
        step_id,
    )


async def search_context(
    conn: asyncpg.Connection,
    query: str,
    limit: int = 10,
) -> list[dict]:
    """Full-text search over context history summaries and data."""
    rows = await conn.fetch(
        """
        SELECT ch.id, ch.session_id, ch.event_type, ch.summary, ch.created_at,
               s.request as session_request
        FROM context_history ch
        JOIN sessions s ON s.id = ch.session_id
        WHERE ch.summary ILIKE $1
           OR s.request ILIKE $1
        ORDER BY ch.created_at DESC
        LIMIT $2
        """,
        f"%{query}%",
        limit,
    )
    return [dict(r) for r in rows]


async def get_session_context(
    conn: asyncpg.Connection,
    session_id: str,
) -> list[dict]:
    """Get all context events for a specific session."""
    rows = await conn.fetch(
        """
        SELECT id, event_type, data, summary, agent, duration_ms, step_id, created_at
        FROM context_history
        WHERE session_id = $1::uuid
        ORDER BY created_at ASC
        """,
        session_id,
    )
    return [dict(r) for r in rows]


# ── Session steps ─────────────────────────────────────────────────────────────

async def create_session_steps(
    conn: asyncpg.Connection,
    session_id: str,
    step_ids: dict[str, str],
) -> None:
    """Insert all 4 steps as pending. Called immediately after create_session."""
    await conn.executemany(
        """
        INSERT INTO session_steps (id, session_id, step_name, status, scheduled_at)
        VALUES ($1::uuid, $2::uuid, $3, 'pending', now())
        """,
        [
            (step_ids["plan"],      session_id, "plan"),
            (step_ids["test"],      session_id, "test"),
            (step_ids["implement"], session_id, "implement"),
            (step_ids["review"],    session_id, "review"),
        ],
    )


async def mark_step_running(
    conn: asyncpg.Connection,
    session_id: str,
    step_name: str,
) -> str | None:
    """Set step to running, record started_at. Returns the step UUID or None if not found."""
    row = await conn.fetchrow(
        """
        UPDATE session_steps
        SET status = 'running', started_at = now()
        WHERE session_id = $1::uuid AND step_name = $2
          AND status IN ('pending', 'running', 'failed')
        RETURNING id
        """,
        session_id,
        step_name,
    )
    return str(row["id"]) if row else None


async def mark_step_finished(
    conn: asyncpg.Connection,
    step_id: str,
) -> None:
    await conn.execute(
        """
        UPDATE session_steps
        SET status = 'finished', ended_at = now()
        WHERE id = $1::uuid
        """,
        step_id,
    )


async def mark_step_finished_by_name(
    conn: asyncpg.Connection,
    session_id: str,
    step_name: str,
) -> None:
    """Mark a running step as finished by name. No-op if already finished (safe for retries)."""
    await conn.execute(
        """
        UPDATE session_steps
        SET status = 'finished', ended_at = now()
        WHERE session_id = $1::uuid AND step_name = $2 AND status = 'running'
        """,
        session_id,
        step_name,
    )


async def mark_step_failed(
    conn: asyncpg.Connection,
    step_id: str,
    error_details: str,
) -> None:
    await conn.execute(
        """
        UPDATE session_steps
        SET status = 'failed', ended_at = now(), error_details = $2
        WHERE id = $1::uuid
        """,
        step_id,
        error_details,
    )


async def get_session_steps(
    conn: asyncpg.Connection,
    session_id: str,
) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT id, step_name, status, scheduled_at, started_at, ended_at, error_details
        FROM session_steps
        WHERE session_id = $1::uuid
        ORDER BY
            CASE step_name
                WHEN 'plan'      THEN 1
                WHEN 'test'      THEN 2
                WHEN 'implement' THEN 3
                WHEN 'review'    THEN 4
            END
        """,
        session_id,
    )
    return [dict(r) for r in rows]


# ── Task history ──────────────────────────────────────────────────────────────

async def log_task_history(
    conn: asyncpg.Connection,
    session_id: str,
    iteration: int,
    *,
    reviewer_critique: str = "",
    diff: str = "",
    lint_output: dict | None = None,
    arch_output: dict | None = None,
    is_approved: bool = False,
    lessons_learned: str = "",
) -> None:
    """Insert or ignore a task_history row (idempotent via ON CONFLICT DO NOTHING)."""
    await conn.execute(
        """
        INSERT INTO task_history
            (session_id, iteration, reviewer_critique, diff,
             lint_output, arch_output, is_approved, lessons_learned)
        VALUES ($1::uuid, $2, $3, $4, $5::jsonb, $6::jsonb, $7, $8)
        ON CONFLICT (session_id, iteration) DO NOTHING
        """,
        session_id,
        iteration,
        reviewer_critique,
        diff,
        json.dumps(lint_output or {}),
        json.dumps(arch_output or {}),
        is_approved,
        lessons_learned,
    )


async def get_task_history(
    conn: asyncpg.Connection,
    session_id: str,
) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT iteration, reviewer_critique, diff,
               lint_output, arch_output, is_approved, lessons_learned, created_at
        FROM task_history
        WHERE session_id = $1::uuid
        ORDER BY iteration ASC
        """,
        session_id,
    )
    return [dict(r) for r in rows]


async def get_session_retry_count(
    conn: asyncpg.Connection,
    session_id: str,
) -> int:
    """Return the number of rejected review iterations logged for this session."""
    row = await conn.fetchrow(
        "SELECT COUNT(*) AS cnt FROM task_history WHERE session_id = $1::uuid",
        session_id,
    )
    return int(row["cnt"]) if row else 0
