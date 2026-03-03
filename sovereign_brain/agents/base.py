"""Base utilities: prompt loading, input/output models, shared types."""

from pathlib import Path
from pydantic import BaseModel

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


class ReviewerOutput(BaseModel):
    approved: bool
    feedback: str
    issues: list[dict] = []
    vibe_score: int = 8
    vibe_notes: str = ""
    required_changes: list[str] = []
