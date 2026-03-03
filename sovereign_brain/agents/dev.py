"""Dev agent — Green phase: write minimal code to make failing tests pass."""

from sovereign_brain.agents.base import (
    AgentInstruction,
    DevInput,
    load_prompt,
)


def build_instruction(input: DevInput, session_id: str) -> AgentInstruction:
    """
    Build a complete AgentInstruction for the Dev agent (Green phase).
    Claude CLI will receive this and implement the minimal passing code.
    """
    system_prompt = load_prompt("dev")

    parts = [
        f"## Failing Test\n### File: `{input.test_file_path}`\n"
        f"```python\n{input.test_code}\n```"
    ]

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
        "- Write MINIMUM code to make the test pass\n"
        "- Do not modify the test file\n"
        "- Use UUIDv7 for any entity IDs\n"
        "- Return code and file_path"
    )

    user_message = "\n\n".join(parts)

    return AgentInstruction(
        agent="dev",
        system_prompt=system_prompt,
        user_message=user_message,
        action_required=(
            "Execute the Dev agent: implement the minimal production code to make the "
            "failing test pass. Write the file to disk and run the test suite to confirm "
            "it PASSES. If tests still fail, call implement_logic again with the new "
            "error_output (up to 3 retries)."
        ),
        session_id=session_id,
        step="implement",
        context={"test_file_path": input.test_file_path},
    )
