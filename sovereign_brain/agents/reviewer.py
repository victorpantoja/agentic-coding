"""Reviewer agent — final quality gate and vibe compliance check.

Three instruction builders are provided for the autonomous orchestrator:
  build_lint_instruction     → LintAgent persona (phase: review_lint)
  build_arch_instruction     → ArchitectureAgent persona (phase: review_arch)
  build_manager_instruction  → ManagerReviewer persona (phase: review_final)

The original build_instruction() is kept for backward compatibility.
"""

from __future__ import annotations

import json
from typing import Any

from sovereign_brain.agents.base import (
    AgentInstruction,
    ArchitectureResult,
    LintResult,
    PhaseInstruction,
    ReviewerInput,
    ReviewerOutput,
    load_prompt,
)

# ── Original instruction builder (backward compat) ───────────────────────────


def build_instruction(input: ReviewerInput, session_id: str) -> AgentInstruction:
    """
    Build a complete AgentInstruction for the Reviewer agent.
    Claude CLI will receive this and perform the final quality review.
    """
    system_prompt = load_prompt("reviewer")

    parts = []

    if input.plan:
        parts.append(f"## Original Plan\n```json\n{json.dumps(input.plan, indent=2)}\n```")

    if input.diff:
        parts.append(f"## Git Diff\n```diff\n{input.diff}\n```")

    if input.changed_files:
        parts.append("## Changed Files")
        for path, code in input.changed_files.items():
            ext = path.split(".")[-1] if "." in path else ""
            parts.append(f"### {path}\n```{ext}\n{code}\n```")

    if input.project_context:
        parts.append(f"## Project Context\n{input.project_context}")

    if input.lint_results:
        ruff_out = input.lint_results.get("ruff") or "✓ clean"
        mypy_out = input.lint_results.get("mypy") or "✓ clean"
        parts.append(
            f"## Linter Results\n"
            f"### ruff\n```\n{ruff_out}\n```\n"
            f"### mypy\n```\n{mypy_out}\n```"
        )

    parts.append(
        "## Review Checklist\n"
        "- [ ] All tests pass\n"
        "- [ ] ruff check passes (no lint errors)\n"
        "- [ ] mypy passes (no type errors)\n"
        "- [ ] Entity IDs use UUIDv7\n"
        "- [ ] DDD boundaries respected\n"
        "- [ ] No security vulnerabilities\n"
        "- [ ] Code follows project conventions\n"
        "- [ ] Vibe score >= 6\n"
        "- [ ] No obvious performance bottlenecks"
    )

    user_message = "\n\n".join(parts)

    return AgentInstruction(
        agent="reviewer",
        system_prompt=system_prompt,
        user_message=user_message,
        action_required=(
            "Execute the Reviewer agent: review the diff and changed files against the "
            "original plan. Return approved (bool), feedback, issues list, vibe_score (1-10), "
            "and required_changes. If approved=false, call start_session again with the "
            "review feedback to iterate."
        ),
        session_id=session_id,
        step="review",
        context={"has_diff": bool(input.diff)},
    )


# ── Autonomous orchestrator builders ─────────────────────────────────────────


def build_lint_instruction(
    input: ReviewerInput, session_id: str, retry_count: int
) -> PhaseInstruction:
    """
    PhaseInstruction for the LintAgent sub-agent persona (phase: review_lint).
    Claude will run ruff + mypy and return a LintResult.
    """
    system_prompt = load_prompt("lint_agent")

    parts: list[str] = []

    if input.changed_files:
        parts.append("## Changed Files")
        for path, code in input.changed_files.items():
            ext = path.split(".")[-1] if "." in path else ""
            parts.append(f"### {path}\n```{ext}\n{code}\n```")

    if input.diff:
        parts.append(f"## Git Diff\n```diff\n{input.diff}\n```")

    if input.project_context:
        parts.append(f"## Project Context\n{input.project_context}")

    if retry_count > 0:
        parts.append(
            f"## Retry Context\nThis is retry #{retry_count}. "
            "Previous iterations failed — ensure ALL lint errors are resolved."
        )

    user_message = "\n\n".join(parts)

    return PhaseInstruction(
        session_id=session_id,
        current_phase="review_lint",
        system_prompt=system_prompt,
        user_message=user_message,
        action_required=(
            "You are the LintAgent. Run `uv run ruff check . --output-format=concise` and "
            "`uv run mypy --ignore-missing-imports --no-error-summary .` via your Bash tool. "
            "Copy the full terminal output verbatim into raw_ruff_output and raw_mypy_output. "
            "Set passed=true only if both commands produce zero errors. "
            "Return a JSON object matching output_schema exactly."
        ),
        output_schema=LintResult.model_json_schema(),
        retry_count=retry_count,
    )


def build_arch_instruction(
    input: ReviewerInput, lint_result: dict[str, Any], session_id: str
) -> PhaseInstruction:
    """
    PhaseInstruction for the ArchitectureAgent sub-agent persona (phase: review_arch).
    Claude will analyse SOLID/DDD compliance and return an ArchitectureResult.
    """
    system_prompt = load_prompt("architecture_agent")

    parts: list[str] = []

    if input.changed_files:
        parts.append("## Changed Files")
        for path, code in input.changed_files.items():
            ext = path.split(".")[-1] if "." in path else ""
            parts.append(f"### {path}\n```{ext}\n{code}\n```")

    if input.diff:
        parts.append(f"## Git Diff\n```diff\n{input.diff}\n```")

    if input.plan:
        parts.append(
            f"## Original Architecture Plan\n```json\n{json.dumps(input.plan, indent=2)}\n```"
        )

    if lint_result:
        lint_summary = (
            f"passed={lint_result.get('passed')}, "
            f"issues_count={len(lint_result.get('issues', []))}"
        )
        parts.append(f"## LintAgent Result Summary\n{lint_summary}")

    if input.project_context:
        parts.append(f"## Project Context\n{input.project_context}")

    user_message = "\n\n".join(parts)

    return PhaseInstruction(
        session_id=session_id,
        current_phase="review_arch",
        system_prompt=system_prompt,
        user_message=user_message,
        action_required=(
            "You are the ArchitectureAgent. Inspect the changed files for SOLID violations, "
            "DDD boundary leaks, and UUIDv7 compliance. "
            "Return a JSON object matching output_schema exactly."
        ),
        output_schema=ArchitectureResult.model_json_schema(),
    )


def build_manager_instruction(
    input: ReviewerInput,
    lint_result: dict[str, Any],
    arch_result: dict[str, Any],
    session_id: str,
) -> PhaseInstruction:
    """
    PhaseInstruction for the ManagerReviewer persona (phase: review_final).
    Claude synthesises both sub-agent results and delivers the final gate decision.
    """
    system_prompt = load_prompt("reviewer")

    parts: list[str] = []

    if input.plan:
        parts.append(f"## Original Plan\n```json\n{json.dumps(input.plan, indent=2)}\n```")

    if input.diff:
        parts.append(f"## Git Diff\n```diff\n{input.diff}\n```")

    if input.changed_files:
        parts.append("## Changed Files")
        for path, code in input.changed_files.items():
            ext = path.split(".")[-1] if "." in path else ""
            parts.append(f"### {path}\n```{ext}\n{code}\n```")

    if lint_result:
        parts.append(
            f"## LintAgent Report\n```json\n{json.dumps(lint_result, indent=2)}\n```"
        )

    if arch_result:
        parts.append(
            f"## ArchitectureAgent Report\n```json\n{json.dumps(arch_result, indent=2)}\n```"
        )

    if input.project_context:
        parts.append(f"## Project Context\n{input.project_context}")

    lint_passed = bool(lint_result.get("passed", False))
    arch_passed = bool(arch_result.get("passed", False))

    parts.append(
        "## Hard Gate Rule\n"
        "**RULE**: If `lint_result.passed` is `false` OR `arch_result.passed` is `false`, "
        "you MUST set `approved=false`. Non-negotiable — overrides all other judgement.\n\n"
        f"LintAgent passed: **{lint_passed}**\n"
        f"ArchitectureAgent passed: **{arch_passed}**"
    )

    parts.append(
        "## Review Checklist\n"
        "- [ ] All tests pass\n"
        "- [ ] ruff check passes (see LintAgent report)\n"
        "- [ ] mypy passes (see LintAgent report)\n"
        "- [ ] Entity IDs use UUIDv7\n"
        "- [ ] DDD boundaries respected (see ArchitectureAgent report)\n"
        "- [ ] No security vulnerabilities\n"
        "- [ ] Code follows project conventions\n"
        "- [ ] Vibe score >= 6\n"
        "- [ ] No obvious performance bottlenecks"
    )

    user_message = "\n\n".join(parts)

    return PhaseInstruction(
        session_id=session_id,
        current_phase="review_final",
        system_prompt=system_prompt,
        user_message=user_message,
        action_required=(
            "You are the ManagerReviewer. Both sub-agent reports are above. "
            "Apply the Hard Gate Rule: if either sub-agent passed=false, set approved=false. "
            "Then apply your own quality judgement for correctness, security, and vibe. "
            "Return a JSON object matching output_schema exactly."
        ),
        output_schema=ReviewerOutput.model_json_schema(),
    )
