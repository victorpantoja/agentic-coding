"""Dev agent — implement code from a plan or make failing tests pass."""

from __future__ import annotations

import json

from sovereign_brain.agents.base import (
    AgentInstruction,
    DevInput,
    load_prompt,
)


def build_instruction(input: DevInput, session_id: str) -> AgentInstruction:
    """
    Build a complete AgentInstruction for the Dev agent.

    When input.plan is provided (initial implement phase), Claude writes the code
    from the architecture plan.  When input.test_code is provided (retry cycle),
    Claude fixes the failing test.
    """
    system_prompt = load_prompt("dev")
    parts: list[str] = []

    if input.test_code:
        parts.append(
            f"## Failing Test\n### File: `{input.test_file_path}`\n"
            f"```python\n{input.test_code}\n```"
        )
    elif input.plan:
        parts.append(
            f"## Implementation Task\n"
            f"```json\n{json.dumps(input.plan, indent=2)}\n```"
        )

    if input.error_output:
        parts.append(f"## Error Output\n```\n{input.error_output}\n```")

    if input.project_context:
        parts.append(f"## Project Context\n{input.project_context}")

    if input.existing_code:
        parts.append("## Existing Code")
        for path, code in input.existing_code.items():
            parts.append(f"### {path}\n```python\n{code}\n```")

    parts.append(
        "## Requirements\n"
        "- Write MINIMUM code to satisfy the task\n"
        "- Use UUIDv7 (`from uuid_extensions import uuid7`) for any entity IDs\n"
        "- Do not modify test files\n"
        "- Return code and file_path"
    )

    user_message = "\n\n".join(parts)

    return AgentInstruction(
        agent="dev",
        system_prompt=system_prompt,
        user_message=user_message,
        action_required=(
            "Execute the Dev agent: implement the code to satisfy the task above. "
            "Write the file to disk. If a test file exists, run the test suite to confirm "
            "it PASSES. If tests still fail, call advance_task again with the new "
            "error_output (up to 3 retries)."
        ),
        session_id=session_id,
        step="implement",
        context={"test_file_path": input.test_file_path} if input.test_file_path else {},
    )
