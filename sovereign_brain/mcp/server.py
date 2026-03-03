"""
Sovereign Brain — FastMCP Server
=================================
Exposes 5 tools to Claude CLI:
  1. start_session    — Architect generates a structural plan
  2. get_test_spec    — Tester generates failing-test spec
  3. implement_logic  — Dev agent generates implementation guide
  4. run_review       — Reviewer performs final quality gate
  5. fetch_context    — Query PostgreSQL for historical context

No external API calls are made.  Each tool returns an AgentInstruction
that Claude CLI executes using its own LLM capability (Teams subscription).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

import asyncpg
from fastmcp import FastMCP
from pydantic import Field

from sovereign_brain.agents import architect, dev, reviewer, tester
from sovereign_brain.agents.base import AgentInstruction
from sovereign_brain.config import Settings
from sovereign_brain.db import queries


# ── App lifespan ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastMCP) -> AsyncIterator[dict[str, Any]]:
    settings = Settings()
    pool = await asyncpg.create_pool(settings.database_url, min_size=2, max_size=10)
    try:
        yield {"pool": pool}
    finally:
        await pool.close()


# ── Server setup ─────────────────────────────────────────────────────────────

mcp = FastMCP(
    name="sovereign-brain",
    instructions=(
        "Sovereign Engineering Office — Local Multi-Agent Brain.\n\n"
        "This server orchestrates four specialized agents (Architect, Tester, Dev, Reviewer) "
        "following the Canon TDD workflow. Each tool returns a structured AgentInstruction "
        "that YOU (Claude CLI) must execute using your own reasoning and the provided system prompt.\n\n"
        "Typical flow:\n"
        "  1. start_session(request)       → Architect produces a plan\n"
        "  2. get_test_spec(plan)          → Tester writes failing tests\n"
        "  3. implement_logic(test_result) → Dev implements minimal code\n"
        "  4. run_review(diff)             → Reviewer approves or requests changes\n"
        "  5. fetch_context(query)         → Look up historical sessions\n\n"
        "If the Reviewer rejects, call start_session again with review_feedback to iterate."
    ),
    lifespan=lifespan,
)


def _new_uuid7() -> str:
    """Generate a UUID7 (time-ordered). Falls back to UUID4 if uuid7 package absent."""
    try:
        from uuid7 import uuid7
        return str(uuid7())
    except ImportError:
        return str(uuid.uuid4())


# ── Tool 1: start_session ────────────────────────────────────────────────────

@mcp.tool()
async def start_session(
    request: Annotated[str, Field(description="The feature request or task description")],
    project_context: Annotated[
        str,
        Field(description="Optional: current project architecture, tech stack, conventions"),
    ] = "",
    review_feedback: Annotated[
        str,
        Field(description="Optional: Reviewer feedback from a previous rejected session (for iteration)"),
    ] = "",
) -> AgentInstruction:
    """
    Trigger the Architect agent to analyse the request and produce a structural plan.

    Returns an AgentInstruction. YOU must execute the system_prompt + user_message
    to produce the architecture plan, then call get_test_spec(plan) with the result.
    """
    ctx = mcp.get_context()
    pool: asyncpg.Pool = ctx.request_context.lifespan_context["pool"]

    session_id = _new_uuid7()

    async with pool.acquire() as conn:
        await queries.create_session(conn, session_id, request)
        await queries.append_context(
            conn,
            _new_uuid7(),
            session_id,
            "plan",
            {"request": request, "project_context": project_context},
            summary=f"Session started: {request[:200]}",
        )

    return architect.build_instruction(
        architect.ArchitectInput(
            request=request,
            project_context=project_context,
            review_feedback=review_feedback,
        ),
        session_id=session_id,
    )


# ── Tool 2: get_test_spec ────────────────────────────────────────────────────

@mcp.tool()
async def get_test_spec(
    plan: Annotated[
        dict,
        Field(description="The architecture plan produced by start_session (ArchitectOutput JSON)"),
    ],
    session_id: Annotated[str, Field(description="Session ID from start_session")],
    scenario: Annotated[
        str,
        Field(
            description=(
                "Specific test scenario to focus on. "
                "Leave empty to derive automatically from the plan."
            ),
        ),
    ] = "",
    existing_code: Annotated[
        dict[str, str],
        Field(description="Map of file_path → code for any existing relevant files"),
    ] = {},
    project_context: Annotated[str, Field(description="Project context")] = "",
) -> AgentInstruction:
    """
    Trigger the Tester agent to write a failing test (Red phase of Canon TDD).

    Pass the plan from start_session. Returns an AgentInstruction with a full
    system prompt + test specification. YOU must write the test file and confirm it fails.
    """
    ctx = mcp.get_context()
    pool: asyncpg.Pool = ctx.request_context.lifespan_context["pool"]

    if not scenario and plan.get("implementation_phases"):
        scenario = f"Implement: {plan['implementation_phases'][0]}"
    elif not scenario and plan.get("components"):
        first = plan["components"][0]
        name = first.get("name", "primary component") if isinstance(first, dict) else str(first)
        scenario = f"Implement core behaviour of {name}"

    async with pool.acquire() as conn:
        await queries.update_session_plan(conn, session_id, plan)
        await queries.append_context(
            conn,
            _new_uuid7(),
            session_id,
            "test",
            {"scenario": scenario, "plan_summary": plan.get("architecture_plan", "")[:500]},
            summary=f"Tester: {scenario[:200]}",
        )

    return tester.build_instruction(
        tester.TesterInput(
            plan=plan,
            scenario=scenario,
            existing_code=existing_code,
            project_context=project_context,
        ),
        session_id=session_id,
    )


# ── Tool 3: implement_logic ──────────────────────────────────────────────────

@mcp.tool()
async def implement_logic(
    test_code: Annotated[str, Field(description="The failing test code written by the Tester")],
    test_file_path: Annotated[str, Field(description="Path where the test file is saved")],
    session_id: Annotated[str, Field(description="Session ID from start_session")],
    error_output: Annotated[
        str,
        Field(description="Test runner error output (required on retry to give the Dev agent context)"),
    ] = "",
    existing_code: Annotated[
        dict[str, str],
        Field(description="Map of file_path → existing code"),
    ] = {},
    project_context: Annotated[str, Field(description="Project context")] = "",
) -> AgentInstruction:
    """
    Trigger the Dev agent to write the minimum code to make the failing test pass (Green phase).

    After receiving the instruction, YOU must write the implementation file and run the tests.
    If tests still fail, call implement_logic again with error_output populated (up to 3 times).
    """
    ctx = mcp.get_context()
    pool: asyncpg.Pool = ctx.request_context.lifespan_context["pool"]

    async with pool.acquire() as conn:
        await queries.update_session_test_spec(
            conn,
            session_id,
            {"test_code": test_code, "test_file_path": test_file_path},
        )
        await queries.append_context(
            conn,
            _new_uuid7(),
            session_id,
            "implement",
            {
                "test_file_path": test_file_path,
                "has_error": bool(error_output),
                "error_preview": error_output[:300] if error_output else "",
            },
            summary=f"Dev: implement for {test_file_path}" + (" (retry)" if error_output else ""),
        )

    return dev.build_instruction(
        dev.DevInput(
            test_code=test_code,
            test_file_path=test_file_path,
            error_output=error_output,
            existing_code=existing_code,
            project_context=project_context,
        ),
        session_id=session_id,
    )


# ── Tool 4: run_review ───────────────────────────────────────────────────────

@mcp.tool()
async def run_review(
    diff: Annotated[
        str,
        Field(description="Git diff (output of `git diff` or `git diff HEAD`) of the changes"),
    ],
    session_id: Annotated[str, Field(description="Session ID from start_session")],
    changed_files: Annotated[
        dict[str, str],
        Field(description="Map of file_path → full file content for all changed files"),
    ] = {},
    plan: Annotated[
        dict,
        Field(description="Original architecture plan for compliance check"),
    ] = {},
    project_context: Annotated[str, Field(description="Project context")] = "",
) -> AgentInstruction:
    """
    Trigger the Reviewer agent for the final quality gate and vibe compliance check.

    Returns an AgentInstruction. YOU must execute the review and return a ReviewerOutput.
    If approved=false, call start_session with review_feedback to begin a new iteration.
    """
    ctx = mcp.get_context()
    pool: asyncpg.Pool = ctx.request_context.lifespan_context["pool"]

    async with pool.acquire() as conn:
        await queries.append_context(
            conn,
            _new_uuid7(),
            session_id,
            "review",
            {"diff_preview": diff[:500], "changed_files": list(changed_files.keys())},
            summary=f"Reviewer: {len(changed_files)} files changed",
        )

    return reviewer.build_instruction(
        reviewer.ReviewerInput(
            diff=diff,
            changed_files=changed_files,
            project_context=project_context,
            plan=plan,
        ),
        session_id=session_id,
    )


# ── Tool 5: fetch_context ────────────────────────────────────────────────────

@mcp.tool()
async def fetch_context(
    query: Annotated[
        str,
        Field(description="Search query — keywords from past requests, plans, or implementations"),
    ],
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
    Query the PostgreSQL database for historical context.

    Returns matching sessions and context events to help with understanding
    past decisions, patterns, and prior implementations.
    """
    ctx = mcp.get_context()
    pool: asyncpg.Pool = ctx.request_context.lifespan_context["pool"]

    async with pool.acquire() as conn:
        if session_id:
            events = await queries.get_session_context(conn, session_id)
            session = await queries.get_session(conn, session_id)
            return {
                "session": _serialize(session),
                "events": [_serialize(e) for e in events],
                "total": len(events),
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
    settings = Settings()
    mcp.run(transport="sse", host=settings.mcp_host, port=settings.mcp_port)


if __name__ == "__main__":
    main()
