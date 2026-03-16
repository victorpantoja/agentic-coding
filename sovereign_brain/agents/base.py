"""Base utilities: prompt loading, input/output models, shared types."""

from pathlib import Path

from pydantic import BaseModel, field_validator

PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(agent_name: str) -> str:
    """Load system prompt from agents/prompts/{agent_name}.md."""
    return (PROMPTS_DIR / f"{agent_name}.md").read_text()


# ── Shared input/output models ────────────────────────────────────────────────

class AgentInstruction(BaseModel):
    """
    Returned by every MCP tool.  Claude CLI reads this and acts on it directly
    — no external API call is made by the server.
    """
    agent: str
    system_prompt: str
    user_message: str
    action_required: str
    session_id: str
    step: str  # 'plan' | 'test' | 'implement' | 'review'
    context: dict = {}


class ArchitectInput(BaseModel):
    request: str
    project_context: str = ""
    review_feedback: str = ""


class ArchitectOutput(BaseModel):
    architecture_plan: str
    components: list[dict]
    bounded_contexts: list[str] = []
    data_models: list[dict] = []
    implementation_phases: list[str] = []


class TesterInput(BaseModel):
    plan: dict
    scenario: str
    existing_code: dict[str, str] = {}
    project_context: str = ""


class TesterOutput(BaseModel):
    test_code: str
    test_file_path: str
    imports_needed: list[str] = []
    expected_behavior: str = ""
    failure_reason: str = ""


class DevInput(BaseModel):
    test_code: str
    test_file_path: str
    error_output: str = ""
    existing_code: dict[str, str] = {}
    project_context: str = ""


class DevOutput(BaseModel):
    code: str
    file_path: str
    dependencies_added: list[str] = []
    explanation: str = ""


class ReviewerInput(BaseModel):
    diff: str
    changed_files: dict[str, str] = {}
    project_context: str = ""
    plan: dict = {}
    lint_results: dict = {}  # {"ruff": "...", "mypy": "...", "errors": bool}


class ReviewerOutput(BaseModel):
    approved: bool
    feedback: str
    issues: list[dict] = []
    vibe_score: int = 8
    vibe_notes: str = ""
    required_changes: list[str] = []


# ── Autonomous orchestrator models ────────────────────────────────────────────

class LintResult(BaseModel):
    """Produced by Claude acting as LintAgent (review_lint phase)."""

    passed: bool
    issues: list[str] = []
    raw_ruff_output: str  # full terminal output verbatim — required even when clean
    raw_mypy_output: str  # full terminal output verbatim — required even when clean


class ArchitectureResult(BaseModel):
    """Produced by Claude acting as ArchitectureAgent (review_arch phase)."""

    passed: bool
    violations: list[str] = []
    notes: str = ""
    raw_analysis: str = ""  # full reasoning — allows Dev agent to parse tracebacks


class IterationLog(BaseModel):
    """One Dev→Reviewer cycle stored in task_history."""

    iteration: int
    reviewer_critique: str
    diff: str
    lint_passed: bool
    arch_passed: bool
    is_approved: bool
    lessons_learned: str  # single-sentence distillation for context injection


class PhaseInstruction(BaseModel):
    """
    Returned by execute_autonomous_task and advance_task.

    Claude CLI must:
      1. Execute system_prompt + user_message using its own reasoning.
      2. Produce a JSON result that matches output_schema.
      3. Call advance_task(session_id, current_phase, result) immediately.
      4. Repeat until is_terminal=True.
    """

    session_id: str
    current_phase: str  # plan|test|implement|review_lint|review_arch|review_final|complete|failed
    system_prompt: str
    user_message: str
    action_required: str
    output_schema: dict  # model_json_schema() of the expected result type
    retry_count: int = 0
    context: dict = {}  # injected lessons_learned from previous retries
    is_terminal: bool = False  # True for complete/failed — stop the loop

    @field_validator("output_schema", mode="before")
    @classmethod
    def ensure_schema_populated(cls, v: dict) -> dict:
        if not v:
            raise ValueError("output_schema must be populated via model_json_schema()")
        return v
