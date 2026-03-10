"""Architect agent — structural planning, DDD/UUIDv7 enforcement."""

import json

from sovereign_brain.agents.base import (
    AgentInstruction,
    ArchitectInput,
    load_prompt,
)


def build_instruction(input: ArchitectInput, session_id: str) -> AgentInstruction:
    """
    Build a complete AgentInstruction for the Architect.
    Claude CLI will receive this and execute the architectural analysis.
    """
    system_prompt = load_prompt("architect")

    parts = [f"## Feature Request\n{input.request}"]

    if input.project_context:
        parts.append(f"## Project Context\n{input.project_context}")

    if input.review_feedback:
        parts.append(f"## Review Feedback (iteration)\n{input.review_feedback}")

    parts.append(
        "## Requirements\n"
        "- All entity IDs must use UUIDv7 (timestamp-ordered)\n"
        "- Apply DDD bounded contexts where appropriate\n"
        "- Design for Canon TDD: each component must be independently testable\n"
        "- Produce an ordered list of implementation phases"
    )

    user_message = "\n\n".join(parts)

    return AgentInstruction(
        agent="architect",
        system_prompt=system_prompt,
        user_message=user_message,
        action_required=(
            "Execute the Architect agent using the system_prompt and user_message above. "
            "Produce a structured architecture plan and return it as a JSON object matching "
            "ArchitectOutput (keys: architecture_plan, components, bounded_contexts, "
            "data_models, implementation_phases). "
            "Then call get_test_spec with: "
            "  plan=<that JSON object as a dict, NOT a string>, "
            f" session_id='{session_id}' "
            "(use exactly this session_id — it must not be omitted or changed)."
        ),
        session_id=session_id,
        step="plan",
        context={"request": input.request},
    )
