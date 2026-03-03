"""Raw asyncpg query helpers for sessions and context history."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

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
) -> None:
    await conn.execute(
        """
        INSERT INTO context_history (id, session_id, event_type, data, summary)
        VALUES ($1::uuid, $2::uuid, $3, $4::jsonb, $5)
        """,
        context_id,
        session_id,
        event_type,
        json.dumps(data),
        summary,
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
        SELECT id, event_type, data, summary, created_at
        FROM context_history
        WHERE session_id = $1::uuid
        ORDER BY created_at ASC
        """,
        session_id,
    )
    return [dict(r) for r in rows]
