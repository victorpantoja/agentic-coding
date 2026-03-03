"""Reviewer agent — final quality gate and vibe compliance check."""

import json

from sovereign_brain.agents.base import (
    AgentInstruction,
    ReviewerInput,
    load_prompt,
)


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

    parts.append(
        "## Review Checklist\n"
        "- [ ] All tests pass\n"
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
