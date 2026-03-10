"""Unit tests for the four agent instruction builders."""

import pytest

import sovereign_brain.agents.architect as _architect_mod
import sovereign_brain.agents.dev as _dev_mod
import sovereign_brain.agents.reviewer as _reviewer_mod
import sovereign_brain.agents.tester as _tester_mod
from sovereign_brain.agents.base import (
    AgentInstruction,
    ArchitectInput,
    DevInput,
    ReviewerInput,
    TesterInput,
)

architect_build = _architect_mod.build_instruction
dev_build = _dev_mod.build_instruction
reviewer_build = _reviewer_mod.build_instruction
make_test_spec = _tester_mod.build_instruction  # avoid 'tester_build' starting with 'test'

SESSION = "01900000-0000-7000-8000-000000000001"
PLAN = {
    "architecture_plan": "A simple REST service with domain layer.",
    "components": [{"name": "UserService", "purpose": "Handles user CRUD"}],
    "implementation_phases": ["Create UserService", "Add endpoints"],
}


class TestArchitectAgent:
    def test_build_instruction_returns_agent_instruction(self):
        result = architect_build(
            ArchitectInput(request="Add user registration"), session_id=SESSION
        )
        assert isinstance(result, AgentInstruction)

    def test_agent_name_is_architect(self):
        result = architect_build(
            ArchitectInput(request="Add user registration"), session_id=SESSION
        )
        assert result.agent == "architect"

    def test_step_is_plan(self):
        result = architect_build(
            ArchitectInput(request="x"), session_id=SESSION
        )
        assert result.step == "plan"

    def test_session_id_is_preserved(self):
        result = architect_build(
            ArchitectInput(request="x"), session_id=SESSION
        )
        assert result.session_id == SESSION

    def test_system_prompt_is_non_empty(self):
        result = architect_build(
            ArchitectInput(request="x"), session_id=SESSION
        )
        assert len(result.system_prompt) > 100

    def test_user_message_contains_request(self):
        result = architect_build(
            ArchitectInput(request="Build a chat feature"), session_id=SESSION
        )
        assert "Build a chat feature" in result.user_message

    def test_review_feedback_appears_in_message(self):
        result = architect_build(
            ArchitectInput(request="x", review_feedback="Too complex"), session_id=SESSION
        )
        assert "Too complex" in result.user_message

    def test_project_context_appears_in_message(self):
        result = architect_build(
            ArchitectInput(request="x", project_context="FastAPI + PostgreSQL"),
            session_id=SESSION,
        )
        assert "FastAPI + PostgreSQL" in result.user_message


class TestTesterAgent:
    def test_build_instruction_returns_agent_instruction(self):
        result = make_test_spec(
            TesterInput(plan=PLAN, scenario="User can register"), session_id=SESSION
        )
        assert isinstance(result, AgentInstruction)

    def test_agent_name_is_tester(self):
        result = make_test_spec(
            TesterInput(plan=PLAN, scenario="User can register"), session_id=SESSION
        )
        assert result.agent == "tester"

    def test_step_is_test(self):
        result = make_test_spec(
            TesterInput(plan=PLAN, scenario="User can register"), session_id=SESSION
        )
        assert result.step == "test"

    def test_scenario_in_user_message(self):
        result = make_test_spec(
            TesterInput(plan=PLAN, scenario="User can register with email"),
            session_id=SESSION,
        )
        assert "User can register with email" in result.user_message

    def test_existing_code_appears_in_message(self):
        result = make_test_spec(
            TesterInput(
                plan=PLAN,
                scenario="x",
                existing_code={"src/users.py": "class User: pass"},
            ),
            session_id=SESSION,
        )
        assert "src/users.py" in result.user_message


class TestDevAgent:
    def test_build_instruction_returns_agent_instruction(self):
        result = dev_build(
            DevInput(
                test_code="def test_foo(): assert foo() == 1",
                test_file_path="tests/test_foo.py",
            ),
            session_id=SESSION,
        )
        assert isinstance(result, AgentInstruction)

    def test_agent_name_is_dev(self):
        result = dev_build(
            DevInput(test_code="x", test_file_path="tests/t.py"),
            session_id=SESSION,
        )
        assert result.agent == "dev"

    def test_step_is_implement(self):
        result = dev_build(
            DevInput(test_code="x", test_file_path="tests/t.py"),
            session_id=SESSION,
        )
        assert result.step == "implement"

    def test_test_file_path_in_message(self):
        result = dev_build(
            DevInput(test_code="x", test_file_path="tests/unit/test_user.py"),
            session_id=SESSION,
        )
        assert "tests/unit/test_user.py" in result.user_message

    def test_error_output_in_message_when_provided(self):
        result = dev_build(
            DevInput(
                test_code="x",
                test_file_path="t.py",
                error_output="ImportError: cannot import 'foo'",
            ),
            session_id=SESSION,
        )
        assert "ImportError" in result.user_message

    def test_no_error_section_when_empty(self):
        result = dev_build(
            DevInput(test_code="x", test_file_path="t.py", error_output=""),
            session_id=SESSION,
        )
        assert "## Error Output" not in result.user_message


class TestReviewerAgent:
    def test_build_instruction_returns_agent_instruction(self):
        result = reviewer_build(
            ReviewerInput(diff="+ def foo(): return 1"), session_id=SESSION
        )
        assert isinstance(result, AgentInstruction)

    def test_agent_name_is_reviewer(self):
        result = reviewer_build(
            ReviewerInput(diff="x"), session_id=SESSION
        )
        assert result.agent == "reviewer"

    def test_step_is_review(self):
        result = reviewer_build(
            ReviewerInput(diff="x"), session_id=SESSION
        )
        assert result.step == "review"

    def test_diff_appears_in_message(self):
        diff = "+ class UserRepository:\n+     pass"
        result = reviewer_build(
            ReviewerInput(diff=diff), session_id=SESSION
        )
        assert diff in result.user_message

    def test_changed_files_appear_in_message(self):
        result = reviewer_build(
            ReviewerInput(
                diff="+x",
                changed_files={"src/user.py": "class User: pass"},
            ),
            session_id=SESSION,
        )
        assert "src/user.py" in result.user_message

    def test_plan_appears_in_message_when_provided(self):
        result = reviewer_build(
            ReviewerInput(diff="+x", plan=PLAN), session_id=SESSION
        )
        assert "architecture_plan" in result.user_message

    def test_lint_results_appear_in_message(self):
        result = reviewer_build(
            ReviewerInput(
                diff="+x",
                lint_results={"ruff": "src/foo.py:1:1: F401", "mypy": "", "errors": True},
            ),
            session_id=SESSION,
        )
        assert "F401" in result.user_message
        assert "Linter Results" in result.user_message

    def test_clean_lint_results_show_checkmark(self):
        result = reviewer_build(
            ReviewerInput(
                diff="+x",
                lint_results={"ruff": "", "mypy": "", "errors": False},
            ),
            session_id=SESSION,
        )
        assert "✓ clean" in result.user_message

    def test_checklist_includes_ruff_and_mypy(self):
        result = reviewer_build(ReviewerInput(diff="+x"), session_id=SESSION)
        assert "ruff check passes" in result.user_message
        assert "mypy passes" in result.user_message

    def test_architect_action_required_mentions_session_id(self):
        from sovereign_brain.agents.base import ArchitectInput
        import sovereign_brain.agents.architect as _arch
        result = _arch.build_instruction(ArchitectInput(request="x"), session_id=SESSION)
        assert SESSION in result.action_required
        assert "session_id" in result.action_required
