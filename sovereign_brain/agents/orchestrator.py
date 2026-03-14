"""
Autonomous orchestrator — drives the Architect → Tester → Dev → Reviewer gated loop.

The server is the state machine; Claude CLI is the intelligence.
No LLM calls are made here — only DB persistence and PhaseInstruction construction.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

import asyncpg

from sovereign_brain.agents import architect, dev, reviewer, tester
from sovereign_brain.agents.base import (
    ArchitectOutput,
    DevOutput,
    PhaseInstruction,
    TesterOutput,
)
from sovereign_brain.db import queries

logger = logging.getLogger("sovereign_brain.orchestrator")

MAX_RETRIES = 3

# Maps phases that have a backing session_steps row to that row's step_name.
# Review sub-phases all map to the single "review" step.
_PHASE_TO_STEP: dict[str, str] = {
    "plan": "plan",
    "test": "test",
    "implement": "implement",
    "review_lint": "review",
    "review_arch": "review",
    "review_final": "review",
}


def _new_uuid7() -> str:
    try:
        from uuid7 import uuid7

        return str(uuid7())
    except ImportError:
        return str(uuid.uuid4())


# ── Public API ────────────────────────────────────────────────────────────────


async def start(request: str, project_context: str, pool: asyncpg.Pool) -> PhaseInstruction:
    """Create a new session and return the first PhaseInstruction (Architect)."""
    session_id = _new_uuid7()
    step_ids = {k: _new_uuid7() for k in ("plan", "test", "implement", "review")}

    async with pool.acquire() as conn:
        await queries.create_session(conn, session_id, request)
        await queries.create_session_steps(conn, session_id, step_ids)
        await queries.mark_step_running(conn, session_id, "plan")
        await queries.append_context(
            conn,
            _new_uuid7(),
            session_id,
            "plan",
            {"request": request, "project_context": project_context},
            summary=f"Autonomous task started: {request[:200]}",
            agent="orchestrator",
        )

    logger.info("[orchestrator] started session=%s request=%.80s", session_id, request)

    instruction = architect.build_instruction(
        architect.ArchitectInput(request=request, project_context=project_context),
        session_id=session_id,
    )
    return _wrap_as_phase(instruction, "plan", session_id, ArchitectOutput)


async def advance(
    session_id: str,
    completed_phase: str,
    result: dict[str, Any],
    pool: asyncpg.Pool,
) -> PhaseInstruction:
    """
    Accept the result of completed_phase, persist it idempotently,
    and return the next PhaseInstruction.
    """
    async with pool.acquire() as conn:
        session = await queries.get_session(conn, session_id)
        if session is None:
            raise ValueError(f"Session {session_id!r} not found")

        steps = await queries.get_session_steps(conn, session_id)
        history = await queries.get_task_history(conn, session_id)
        lessons = _summarise_lessons(history)

        # ── Idempotency check ────────────────────────────────────────────────
        step_name = _PHASE_TO_STEP.get(completed_phase)
        already_done = False
        if step_name and completed_phase not in ("review_lint", "review_arch"):
            step = next((s for s in steps if s["step_name"] == step_name), None)
            already_done = step is not None and step["status"] == "finished"

        if not already_done:
            await _persist(conn, session_id, completed_phase, result, steps)

        return await _build_next(
            conn, session_id, completed_phase, result, session, lessons, pool
        )


async def get_status(session_id: str, pool: asyncpg.Pool) -> dict[str, Any]:
    """Return the current phase, retry count, and lessons learned for loop recovery."""
    async with pool.acquire() as conn:
        session = await queries.get_session(conn, session_id)
        if session is None:
            raise ValueError(f"Session {session_id!r} not found")

        steps = await queries.get_session_steps(conn, session_id)
        history = await queries.get_task_history(conn, session_id)

        current_phase = _derive_current_phase(steps, session)
        lessons = _summarise_lessons(history)
        last_review = session.get("review") or {}

        return {
            "session_id": session_id,
            "current_phase": current_phase,
            "retry_count": len(history),
            "lessons_learned": lessons,
            "steps": steps,
            "last_review": last_review,
        }


# ── Persistence ───────────────────────────────────────────────────────────────


async def _persist(
    conn: asyncpg.Connection,
    session_id: str,
    phase: str,
    result: dict[str, Any],
    steps: list[dict],
) -> None:
    step_name = _PHASE_TO_STEP.get(phase)

    match phase:
        case "plan":
            await queries.update_session_plan(conn, session_id, result)
            await queries.mark_step_finished_by_name(conn, session_id, "plan")
            await queries.mark_step_running(conn, session_id, "test")

        case "test":
            await queries.update_session_test_spec(conn, session_id, result)
            await queries.mark_step_finished_by_name(conn, session_id, "test")
            await queries.mark_step_running(conn, session_id, "implement")

        case "implement":
            await queries.update_session_implementation(conn, session_id, result)
            await queries.mark_step_finished_by_name(conn, session_id, "implement")
            await queries.mark_step_running(conn, session_id, "review")

        case "review_lint" | "review_arch":
            # Sub-phases: store in context_history; review step stays running
            await queries.append_context(
                conn,
                _new_uuid7(),
                session_id,
                "review",
                {phase: result},
                summary=f"Reviewer sub-agent {phase} completed (passed={result.get('passed')})",
                agent=phase,
            )

        case "review_final":
            # Handled separately in _build_next — requires gate logic
            pass

        case _:
            logger.warning("[orchestrator] unknown phase %r — skipping persist", phase)

    if step_name and phase not in ("review_lint", "review_arch", "review_final"):
        logger.info("[orchestrator] persisted phase=%s session=%s", phase, session_id)


# ── Next instruction builder ──────────────────────────────────────────────────


async def _build_next(
    conn: asyncpg.Connection,
    session_id: str,
    completed_phase: str,
    result: dict[str, Any],
    session: dict[str, Any],
    lessons: str,
    pool: asyncpg.Pool,
) -> PhaseInstruction:
    match completed_phase:
        case "plan":
            plan = result
            instruction = tester.build_instruction(
                tester.TesterInput(
                    plan=plan,
                    scenario=_first_scenario(plan),
                    project_context=session.get("request", ""),
                ),
                session_id=session_id,
            )
            return _wrap_as_phase(instruction, "test", session_id, TesterOutput, lessons=lessons)

        case "test":
            test_code = result.get("test_code", "")
            test_file_path = result.get("test_file_path", "tests/test_generated.py")
            retry_count = await queries.get_session_retry_count(conn, session_id)
            instruction = dev.build_instruction(
                dev.DevInput(
                    test_code=test_code,
                    test_file_path=test_file_path,
                    project_context=session.get("request", ""),
                ),
                session_id=session_id,
            )
            phase_instr = _wrap_as_phase(
                instruction, "implement", session_id, DevOutput, lessons=lessons
            )
            return phase_instr.model_copy(update={"retry_count": retry_count})

        case "implement":
            plan = _json_field(session, "plan")
            implementation = result
            reviewer_input = reviewer.ReviewerInput(
                diff=implementation.get("explanation", ""),
                changed_files={implementation.get("file_path", ""): implementation.get("code", "")},
                plan=plan,
                project_context=session.get("request", ""),
                lint_results={},
            )
            retry_count = await queries.get_session_retry_count(conn, session_id)
            return reviewer.build_lint_instruction(reviewer_input, session_id, retry_count)

        case "review_lint":
            lint_result = result
            # Retrieve implementation from session for arch review
            implementation = _json_field(session, "implementation")
            plan = _json_field(session, "plan")
            reviewer_input = reviewer.ReviewerInput(
                diff=implementation.get("explanation", ""),
                changed_files={implementation.get("file_path", ""): implementation.get("code", "")},
                plan=plan,
                project_context=session.get("request", ""),
                lint_results=lint_result,
            )
            return reviewer.build_arch_instruction(reviewer_input, lint_result, session_id)

        case "review_arch":
            arch_result = result
            # Retrieve lint result from context_history
            ctx_events = await queries.get_session_context(conn, session_id)
            lint_result = _extract_sub_agent_result(ctx_events, "review_lint")
            implementation = _json_field(session, "implementation")
            plan = _json_field(session, "plan")
            reviewer_input = reviewer.ReviewerInput(
                diff=implementation.get("explanation", ""),
                changed_files={implementation.get("file_path", ""): implementation.get("code", "")},
                plan=plan,
                project_context=session.get("request", ""),
                lint_results=lint_result,
            )
            return reviewer.build_manager_instruction(
                reviewer_input, lint_result, arch_result, session_id
            )

        case "review_final":
            return await _handle_review_final(conn, session_id, result, session, lessons)

        case _:
            # Defensive: should not happen
            logger.error("[orchestrator] unexpected completed_phase=%r", completed_phase)
            return PhaseInstruction(
                session_id=session_id,
                current_phase="failed",
                system_prompt="",
                user_message=f"Unexpected phase: {completed_phase!r}",
                action_required="Report this error to the user.",
                output_schema={"type": "object"},
                is_terminal=True,
            )


async def _handle_review_final(
    conn: asyncpg.Connection,
    session_id: str,
    result: dict[str, Any],
    session: dict[str, Any],
    lessons: str,
) -> PhaseInstruction:
    """Apply the hard gate and either approve, retry, or fail."""
    ctx_events = await queries.get_session_context(conn, session_id)
    lint_result = _extract_sub_agent_result(ctx_events, "review_lint")
    arch_result = _extract_sub_agent_result(ctx_events, "review_arch")

    lint_passed = bool(lint_result.get("passed", False))
    arch_passed = bool(arch_result.get("passed", False))
    manager_approved = bool(result.get("approved", False))

    # Hard gate: both sub-agents AND manager must approve
    effective_approved = manager_approved and lint_passed and arch_passed

    retry_count = await queries.get_session_retry_count(conn, session_id)

    # Build critique (used for both the log and the retry instruction)
    critique_parts: list[str] = []
    if not lint_passed:
        issues = lint_result.get("issues") or []
        ruff = lint_result.get("raw_ruff_output", "")
        critique_parts.append(f"Lint failures:\n{ruff or chr(10).join(issues)}")
    if not arch_passed:
        violations = arch_result.get("violations") or []
        critique_parts.append("Architecture violations:\n" + "\n".join(violations))
    if result.get("required_changes"):
        critique_parts.append("Manager required changes:\n" + "\n".join(result["required_changes"]))
    critique = "\n\n".join(critique_parts) or result.get("feedback", "")
    lessons_line = _one_liner_critique(critique, retry_count + 1, lint_passed, arch_passed)

    # Log every iteration — approved or not — so task_history is never empty after a run
    implementation = _json_field(session, "implementation")
    await queries.log_task_history(
        conn,
        session_id,
        retry_count + 1,
        reviewer_critique=critique,
        diff=implementation.get("explanation", ""),
        lint_output=lint_result,
        arch_output=arch_result,
        is_approved=effective_approved,
        lessons_learned=lessons_line,
    )

    if effective_approved:
        await queries.update_session_review(conn, session_id, result, "approved")
        await queries.mark_step_finished_by_name(conn, session_id, "review")
        logger.info(
            "[orchestrator] session=%s APPROVED after %d iteration(s)", session_id, retry_count + 1
        )
        return PhaseInstruction(
            session_id=session_id,
            current_phase="complete",
            system_prompt="",
            user_message=(
                f"Task completed successfully after {retry_count + 1} iteration(s).\n\n"
                f"Reviewer feedback: {result.get('feedback', '')}"
            ),
            action_required="Notify the user that the autonomous task is complete.",
            output_schema={"type": "object"},
            is_terminal=True,
        )

    new_retry_count = retry_count + 1

    if new_retry_count >= MAX_RETRIES:
        await queries.update_session_review(conn, session_id, result, "rejected")
        await queries.mark_step_finished_by_name(conn, session_id, "review")
        logger.warning("[orchestrator] session=%s FAILED after %d retries", session_id, MAX_RETRIES)
        return PhaseInstruction(
            session_id=session_id,
            current_phase="failed",
            system_prompt="",
            user_message=(
                f"The Gated Loop failed after {MAX_RETRIES} retries.\n\n"
                f"Final critique:\n{critique}"
            ),
            action_required=(
                "Notify the user that the autonomous loop has failed and present the critique."
            ),
            output_schema={"type": "object"},
            retry_count=new_retry_count,
            is_terminal=True,
        )

    # Reset implement step for retry
    await conn.execute(
        """
        UPDATE session_steps
        SET status = 'pending', started_at = NULL, ended_at = NULL, error_details = NULL
        WHERE session_id = $1::uuid AND step_name = 'implement'
        """,
        session_id,
    )
    await conn.execute(
        """
        UPDATE session_steps
        SET status = 'pending', started_at = NULL, ended_at = NULL, error_details = NULL
        WHERE session_id = $1::uuid AND step_name = 'review'
        """,
        session_id,
    )
    await queries.mark_step_running(conn, session_id, "implement")

    # Aggregate all lessons for next Dev instruction
    all_history = await queries.get_task_history(conn, session_id)
    all_lessons = _summarise_lessons(all_history)

    test_spec = _json_field(session, "test_spec")
    test_code = test_spec.get("test_code", "")
    test_file_path = test_spec.get("test_file_path", "tests/test_generated.py")

    instruction = dev.build_instruction(
        dev.DevInput(
            test_code=test_code,
            test_file_path=test_file_path,
            error_output=critique,
            project_context=session.get("request", ""),
        ),
        session_id=session_id,
    )
    phase_instr = _wrap_as_phase(
        instruction, "implement", session_id, DevOutput, lessons=all_lessons
    )
    return phase_instr.model_copy(update={"retry_count": new_retry_count})


# ── Helpers ───────────────────────────────────────────────────────────────────


def _json_field(session: dict[str, Any], key: str) -> dict[str, Any]:
    """Decode a JSONB session field — asyncpg returns them as raw JSON strings."""
    value = session.get(key)
    if not value:
        return {}
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value  # already a dict


def _wrap_as_phase(
    instruction: Any,
    phase: str,
    session_id: str,
    result_model: type,
    *,
    lessons: str = "",
    retry_count: int = 0,
) -> PhaseInstruction:
    """Convert an AgentInstruction to a PhaseInstruction."""
    from sovereign_brain.agents.base import AgentInstruction

    assert isinstance(instruction, AgentInstruction)
    ctx: dict[str, Any] = {}
    if lessons:
        ctx["lessons_learned"] = lessons

    return PhaseInstruction(
        session_id=session_id,
        current_phase=phase,
        system_prompt=instruction.system_prompt,
        user_message=instruction.user_message,
        action_required=(
            instruction.action_required
            + "\n\nReturn a JSON object that strictly matches the provided output_schema."
            + (f"\n\nLessons from previous retries: {lessons}" if lessons else "")
        ),
        output_schema=result_model.model_json_schema(),
        retry_count=retry_count,
        context=ctx,
    )


def _summarise_lessons(history: list[dict[str, Any]]) -> str:
    """Distil task_history into a compact lessons string (~200 tokens max)."""
    if not history:
        return ""
    parts = []
    for row in history:
        n = row.get("iteration", "?")
        lesson = row.get("lessons_learned") or row.get("reviewer_critique", "")
        if lesson:
            parts.append(f"Retry {n}: {lesson[:120]}")
    return " | ".join(parts)


def _one_liner_critique(critique: str, iteration: int, lint_passed: bool, arch_passed: bool) -> str:
    failures = []
    if not lint_passed:
        failures.append("lint failed")
    if not arch_passed:
        failures.append("architecture violations")
    reason = ", ".join(failures) or "manager rejected"
    first_line = critique.splitlines()[0][:100] if critique else "review rejected"
    return f"Iteration {iteration} failed ({reason}): {first_line}"


def _first_scenario(plan: dict[str, Any]) -> str:
    phases = plan.get("implementation_phases") or []
    if phases:
        return f"Implement: {phases[0]}"
    components = plan.get("components") or []
    if components:
        first = components[0]
        name = first.get("name", "primary component") if isinstance(first, dict) else str(first)
        return f"Implement core behaviour of {name}"
    return "Implement the primary feature"


def _derive_current_phase(steps: list[dict], session: dict[str, Any]) -> str:
    status_map = {s["step_name"]: s["status"] for s in steps}
    if status_map.get("review") == "finished":
        review_status = session.get("status", "")
        return "complete" if review_status == "approved" else "failed"
    if status_map.get("review") == "running":
        return "review_lint"  # conservative — exact sub-phase not stored
    if status_map.get("implement") == "running":
        return "implement"
    if status_map.get("test") == "running":
        return "test"
    return "plan"


def _extract_sub_agent_result(ctx_events: list[dict], phase: str) -> dict[str, Any]:
    """Pull the latest sub-agent result from context_history events."""
    for event in reversed(ctx_events):
        data = event.get("data") or {}
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                continue
        if phase in data:
            return data[phase]
    return {}
