"""Unit tests for the autonomous reviewer instruction builders."""

from __future__ import annotations

import sovereign_brain.agents.reviewer as _reviewer_mod
from sovereign_brain.agents.base import (
    PhaseInstruction,
    ReviewerInput,
)

SESSION = "01900000-0000-7000-8000-000000000002"

PLAN = {
    "architecture_plan": "REST service with domain layer.",
    "components": [{"name": "HealthService", "purpose": "Returns 200 OK"}],
}

CHANGED_FILES = {"sovereign_brain/health.py": "def health(): return {'status': 'ok'}"}

LINT_RESULT_CLEAN = {
    "passed": True,
    "issues": [],
    "raw_ruff_output": "",
    "raw_mypy_output": "Success: no issues found in 1 source file",
}

LINT_RESULT_FAIL = {
    "passed": False,
    "issues": ["sovereign_brain/health.py:1:1: F401 unused import"],
    "raw_ruff_output": "sovereign_brain/health.py:1:1: F401 unused import",
    "raw_mypy_output": "Success: no issues found in 1 source file",
}

ARCH_RESULT_PASS = {
    "passed": True,
    "violations": [],
    "notes": "No violations.",
    "raw_analysis": "All checks passed.",
}

ARCH_RESULT_FAIL = {
    "passed": False,
    "violations": ["health.py:5 — uuid.uuid4() instead of uuid7()"],
    "notes": "UUID4 used.",
    "raw_analysis": "Line 5 uses uuid.uuid4().",
}


class TestBuildLintInstruction:
    def _make(self, retry_count: int = 0) -> PhaseInstruction:
        return _reviewer_mod.build_lint_instruction(
            ReviewerInput(diff="+def health(): ...", changed_files=CHANGED_FILES),
            session_id=SESSION,
            retry_count=retry_count,
        )

    def test_returns_phase_instruction(self):
        assert isinstance(self._make(), PhaseInstruction)

    def test_current_phase_is_review_lint(self):
        assert self._make().current_phase == "review_lint"

    def test_session_id_preserved(self):
        assert self._make().session_id == SESSION

    def test_output_schema_matches_lint_result(self):
        schema = self._make().output_schema
        assert "passed" in schema.get("properties", {})
        assert "raw_ruff_output" in schema.get("properties", {})

    def test_action_required_mentions_ruff(self):
        instr = self._make()
        assert "ruff" in instr.action_required

    def test_retry_context_injected_when_retry(self):
        instr = self._make(retry_count=2)
        assert "retry" in instr.user_message.lower() or "2" in instr.user_message
        assert instr.retry_count == 2

    def test_changed_files_in_user_message(self):
        instr = self._make()
        assert "sovereign_brain/health.py" in instr.user_message

    def test_system_prompt_loaded(self):
        instr = self._make()
        assert len(instr.system_prompt) > 50
        assert "LintAgent" in instr.system_prompt


class TestBuildArchInstruction:
    def _make(self) -> PhaseInstruction:
        return _reviewer_mod.build_arch_instruction(
            ReviewerInput(
                diff="+def health(): ...",
                changed_files=CHANGED_FILES,
                plan=PLAN,
            ),
            lint_result=LINT_RESULT_CLEAN,
            session_id=SESSION,
        )

    def test_returns_phase_instruction(self):
        assert isinstance(self._make(), PhaseInstruction)

    def test_current_phase_is_review_arch(self):
        assert self._make().current_phase == "review_arch"

    def test_output_schema_matches_architecture_result(self):
        schema = self._make().output_schema
        assert "passed" in schema.get("properties", {})
        assert "violations" in schema.get("properties", {})

    def test_lint_summary_in_user_message(self):
        instr = self._make()
        assert "passed=True" in instr.user_message or "passed" in instr.user_message

    def test_plan_in_user_message_when_provided(self):
        instr = self._make()
        assert "architecture_plan" in instr.user_message

    def test_system_prompt_loaded(self):
        instr = self._make()
        assert "ArchitectureAgent" in instr.system_prompt

    def test_schema_is_populated(self):
        instr = self._make()
        assert instr.output_schema  # non-empty


class TestBuildManagerInstruction:
    def _make(
        self,
        lint: dict | None = None,
        arch: dict | None = None,
    ) -> PhaseInstruction:
        return _reviewer_mod.build_manager_instruction(
            ReviewerInput(
                diff="+def health(): ...",
                changed_files=CHANGED_FILES,
                plan=PLAN,
            ),
            lint_result=lint or LINT_RESULT_CLEAN,
            arch_result=arch or ARCH_RESULT_PASS,
            session_id=SESSION,
        )

    def test_returns_phase_instruction(self):
        assert isinstance(self._make(), PhaseInstruction)

    def test_current_phase_is_review_final(self):
        assert self._make().current_phase == "review_final"

    def test_output_schema_matches_reviewer_output(self):
        schema = self._make().output_schema
        assert "approved" in schema.get("properties", {})
        assert "required_changes" in schema.get("properties", {})

    def test_hard_gate_rule_in_user_message(self):
        instr = self._make()
        assert "Hard Gate" in instr.user_message
        assert "approved=false" in instr.user_message.lower() or "approved" in instr.user_message

    def test_lint_passed_status_shown(self):
        instr = self._make(lint=LINT_RESULT_FAIL)
        assert "False" in instr.user_message or "false" in instr.user_message.lower()

    def test_arch_passed_status_shown(self):
        instr = self._make(arch=ARCH_RESULT_FAIL)
        assert "False" in instr.user_message or "false" in instr.user_message.lower()

    def test_both_reports_embedded(self):
        instr = self._make()
        assert "LintAgent Report" in instr.user_message
        assert "ArchitectureAgent Report" in instr.user_message

    def test_action_required_mentions_hard_gate(self):
        instr = self._make()
        assert "Hard Gate" in instr.action_required or "approved=false" in instr.action_required


class TestBackwardCompatBuildInstruction:
    """Original build_instruction() must still work unchanged."""

    def test_returns_agent_instruction(self):
        from sovereign_brain.agents.base import AgentInstruction

        result = _reviewer_mod.build_instruction(
            ReviewerInput(diff="+x"), session_id=SESSION
        )
        assert isinstance(result, AgentInstruction)

    def test_agent_name_is_reviewer(self):

        result = _reviewer_mod.build_instruction(
            ReviewerInput(diff="+x"), session_id=SESSION
        )
        assert result.agent == "reviewer"
