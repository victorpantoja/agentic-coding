"""Tester agent — Red phase: write failing tests before any implementation."""

from sovereign_brain.agents.base import (
    AgentInstruction,
    TesterInput,
    load_prompt,
)


def build_instruction(input: TesterInput, session_id: str) -> AgentInstruction:
    """
    Build a complete AgentInstruction for the Tester (Red phase).
    Claude CLI will receive this and write the failing test.
    """
    system_prompt = load_prompt("tester")

    parts = [f"## Test Scenario\n{input.scenario}"]

    if input.plan:
        import json
        parts.append(f"## Architecture Plan\n```json\n{json.dumps(input.plan, indent=2)}\n```")

    if input.project_context:
        parts.append(f"## Project Context\n{input.project_context}")

    if input.existing_code:
        parts.append("## Existing Code")
        for path, code in input.existing_code.items():
            parts.append(f"### {path}\n```python\n{code}\n```")

    parts.append(
        "## Requirements\n"
        "- Use pytest with pytest-asyncio for async tests\n"
        "- Test must FAIL before implementation (Red phase)\n"
        "- Import from the production module path even if it doesn't exist yet\n"
        "- Use Arrange/Act/Assert pattern\n"
        "- One assertion per test function when possible"
    )

    user_message = "\n\n".join(parts)

    return AgentInstruction(
        agent="tester",
        system_prompt=system_prompt,
        user_message=user_message,
        action_required=(
            "Execute the Tester agent: write a failing test for the scenario above. "
            "The test must not pass until the Dev agent implements the production code. "
            "Return test_code and test_file_path. Then write the test file to disk and "
            "run it to confirm it FAILS (exit code != 0)."
        ),
        session_id=session_id,
        step="test",
        context={"scenario": input.scenario},
    )
