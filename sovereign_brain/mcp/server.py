"""
Sovereign Brain — FastMCP Server (High-Autonomy Orchestrator)
=============================================================
Exposes four tools to Claude CLI:

  1. execute_autonomous_task  — Start the full Architect→Tester→Dev→Reviewer pipeline.
                                Returns the first PhaseInstruction (Architect phase).

  2. advance_task             — Submit the result of the current phase and receive the next
                                PhaseInstruction. Repeat until is_terminal=True.

  3. get_current_status       — Recovery tool: returns current phase + lessons learned so an
                                interrupted autonomous loop can be resumed without data loss.

  4. fetch_context            — Query PostgreSQL for historical sessions and context.

Architecture (keyless):
  - The Python server handles state, phase transitions, and DB persistence.
  - Claude CLI handles ALL intelligence using the Teams subscription.
  - No ANTHROPIC_API_KEY required — zero in-server LLM calls.

Autonomous loop pattern:
  execute_autonomous_task(request)
    → PhaseInstruction(current_phase="plan")
    → [Claude executes, produces ArchitectOutput JSON]
    → advance_task(session_id, "plan", architect_output)
    → PhaseInstruction(current_phase="test")
    → ... repeat ...
    → PhaseInstruction(current_phase="complete", is_terminal=True)
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

import asyncpg
from fastmcp import Context, FastMCP
from pydantic import Field

from sovereign_brain.agents import orchestrator
from sovereign_brain.agents.base import PhaseInstruction
from sovereign_brain.config import Settings
from sovereign_brain.db import queries

logger = logging.getLogger("sovereign_brain")


# ── App lifespan ──────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastMCP) -> AsyncIterator[dict[str, Any]]:
    settings = Settings()
    pool = await asyncpg.create_pool(settings.database_url, min_size=2, max_size=10)
    try:
        yield {"pool": pool}
    finally:
        await pool.close()


# ── Server setup ──────────────────────────────────────────────────────────────

mcp = FastMCP(
    name="sovereign-brain",
    instructions=(
        "Sovereign Engineering Office — High-Autonomy Orchestrator.\n\n"
        "ARCHITECTURE (keyless): This server drives a state machine. You supply the intelligence.\n"
        "No API key required — all reasoning is performed by you (Claude CLI / Teams).\n\n"
        "AUTONOMOUS LOOP:\n"
        "  1. Call execute_autonomous_task(request)\n"
        "     → Returns PhaseInstruction(current_phase='plan')\n"
        "  2. Execute the instruction using your own reasoning.\n"
        "     Produce a JSON result matching output_schema.\n"
        "  3. Call advance_task(session_id, completed_phase, result)\n"
        "     → Returns the next PhaseInstruction\n"
        "  4. Repeat until is_terminal=True (current_phase='complete' or 'failed').\n\n"
        "REVIEWER SUB-AGENTS:\n"
        "  review_lint  → Act as LintAgent: run `uv run ruff check .` + mypy via Bash.\n"
        "  review_arch  → Act as ArchitectureAgent: check SOLID/DDD/UUIDv7.\n"
        "  review_final → Act as ManagerReviewer: apply Hard Gate + vibe check.\n\n"
        "RECOVERY:\n"
        "  If the loop is interrupted, call get_current_status(session_id) to resume.\n\n"
        "SILENCE IS PROGRESS: only interrupt the user when current_phase is 'complete' or 'failed'."
    ),
    lifespan=lifespan,
)


# ── Tool 1: execute_autonomous_task ───────────────────────────────────────────

@mcp.tool()
async def execute_autonomous_task(
    request: Annotated[str, Field(description="Feature request or task description")],
    ctx: Context,
    project_context: Annotated[
        str,
        Field(description="Current project architecture, tech stack, and conventions"),
    ] = "",
) -> PhaseInstruction:
    """
    Start the autonomous TDD pipeline.

    Creates a new session and returns the first PhaseInstruction (Architect phase).
    YOU must execute the instruction, produce a result matching output_schema, then
    call advance_task(). Repeat until is_terminal=True. Do not interrupt the user between phases.
    """
    pool: asyncpg.Pool = ctx.lifespan_context["pool"]
    logger.info("[server] execute_autonomous_task | request=%.80s", request)
    return await orchestrator.start(request, project_context, pool)


# ── Tool 2: advance_task ──────────────────────────────────────────────────────

@mcp.tool()
async def advance_task(
    session_id: Annotated[str, Field(description="Session ID from execute_autonomous_task")],
    completed_phase: Annotated[
        str,
        Field(
            description=(
                "The phase you just completed: "
                "'plan' | 'test' | 'implement' | 'review_lint' | 'review_arch' | 'review_final'"
            )
        ),
    ],
    result: Annotated[
        dict,
        Field(description="Structured JSON output from executing the last PhaseInstruction"),
    ],
    ctx: Context,
) -> PhaseInstruction:
    """
    Submit the result of the current phase and receive the next PhaseInstruction.

    This method is idempotent: calling it twice with the same session_id and
    completed_phase returns the same next instruction without advancing state twice.

    Keep calling until current_phase == 'complete' or 'failed' (is_terminal=True).
    """
    pool: asyncpg.Pool = ctx.lifespan_context["pool"]
    logger.info(
        "[server] advance_task | session=%s | phase=%s | approved=%s",
        session_id,
        completed_phase,
        result.get("approved", "n/a"),
    )
    return await orchestrator.advance(session_id, completed_phase, result, pool)


# ── Tool 3: get_current_status ────────────────────────────────────────────────

@mcp.tool()
async def get_current_status(
    session_id: Annotated[str, Field(description="Session ID to inspect")],
    ctx: Context,
) -> dict:
    """
    Recovery tool. Returns the current phase, retry count, lessons learned, and step states.

    Call this if the autonomous loop was interrupted to understand where to resume without
    losing context or duplicating work.
    """
    pool: asyncpg.Pool = ctx.lifespan_context["pool"]
    logger.info("[server] get_current_status | session=%s", session_id)
    return await orchestrator.get_status(session_id, pool)


# ── Tool 4: fetch_context ─────────────────────────────────────────────────────

@mcp.tool()
async def fetch_context(
    query: Annotated[
        str,
        Field(description="Search query — keywords from past requests, plans, or implementations"),
    ],
    ctx: Context,
    session_id: Annotated[
        str,
        Field(description="Optional: restrict search to a specific session"),
    ] = "",
    limit: Annotated[
        int,
        Field(description="Max number of context records to return (1-50)"),
    ] = 10,
) -> dict:
    """
    Query PostgreSQL for historical context.

    Returns matching sessions and context events to help understand past decisions,
    patterns, and prior implementations. Also returns task_history for any session.
    """
    pool: asyncpg.Pool = ctx.lifespan_context["pool"]
    logger.info("[server] fetch_context | query=%.80s | session=%s", query, session_id or "*")

    async with pool.acquire() as conn:
        if session_id:
            events = await queries.get_session_context(conn, session_id)
            session = await queries.get_session(conn, session_id)
            steps = await queries.get_session_steps(conn, session_id)
            history = await queries.get_task_history(conn, session_id)
            return {
                "session": _serialize(session),
                "steps": [_serialize(s) for s in steps],
                "events": [_serialize(e) for e in events],
                "task_history": [_serialize(h) for h in history],
                "total_events": len(events),
                "total_iterations": len(history),
            }

        matches = await queries.search_context(conn, query, limit=limit)
        sessions = await queries.list_sessions(conn, limit=limit)

        return {
            "query": query,
            "context_matches": [_serialize(m) for m in matches],
            "recent_sessions": [_serialize(s) for s in sessions],
            "total_matches": len(matches),
        }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _serialize(obj: Any) -> Any:
    """Convert asyncpg Record / non-serializable objects to plain dicts."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(i) for i in obj]
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if hasattr(obj, "__str__") and not isinstance(obj, (str, int, float, bool)):
        return str(obj)
    return obj


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    settings = Settings()
    mcp.run(transport="http", host=settings.mcp_host, port=settings.mcp_port)


if __name__ == "__main__":
    main()
