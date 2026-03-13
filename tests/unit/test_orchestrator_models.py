"""Unit tests for PhaseInstruction and related autonomous orchestrator models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sovereign_brain.agents.base import (
    ArchitectureResult,
    IterationLog,
    LintResult,
    PhaseInstruction,
    ReviewerOutput,
)

SESSION = "01900000-0000-7000-8000-000000000001"


class TestLintResult:
    def test_passed_true_when_no_issues(self):
        r = LintResult(passed=True, raw_ruff_output="", raw_mypy_output="")
        assert r.passed is True
        assert r.issues == []

    def test_passed_false_with_issues(self):
        r = LintResult(
            passed=False,
            issues=["src/foo.py:1:1: F401 unused import"],
            raw_ruff_output="src/foo.py:1:1: F401 unused import",
            raw_mypy_output="Success: no issues found",
        )
        assert r.passed is False
        assert len(r.issues) == 1

    def test_raw_fields_required(self):
        with pytest.raises(ValidationError):
            LintResult(passed=True)  # missing raw_ruff_output and raw_mypy_output

    def test_json_schema_is_populated(self):
        schema = LintResult.model_json_schema()
        assert "passed" in schema.get("properties", {})
        assert "raw_ruff_output" in schema.get("properties", {})
        assert "raw_mypy_output" in schema.get("properties", {})


class TestArchitectureResult:
    def test_passed_true_when_no_violations(self):
        r = ArchitectureResult(passed=True)
        assert r.passed is True
        assert r.violations == []

    def test_passed_false_with_violations(self):
        r = ArchitectureResult(
            passed=False,
            violations=["dev.py:42 — uses uuid.uuid4()"],
            notes="UUIDv7 required.",
        )
        assert not r.passed
        assert len(r.violations) == 1

    def test_json_schema_is_populated(self):
        schema = ArchitectureResult.model_json_schema()
        assert "passed" in schema.get("properties", {})
        assert "violations" in schema.get("properties", {})


class TestIterationLog:
    def test_creates_with_required_fields(self):
        log = IterationLog(
            iteration=1,
            reviewer_critique="Used UUID4",
            diff="+x = 1",
            lint_passed=False,
            arch_passed=False,
            is_approved=False,
            lessons_learned="Retry 1: used uuid4 instead of uuid7",
        )
        assert log.iteration == 1
        assert log.is_approved is False


class TestPhaseInstruction:
    def test_valid_phase_instruction(self):
        pi = PhaseInstruction(
            session_id=SESSION,
            current_phase="plan",
            system_prompt="You are the Architect.",
            user_message="Design a health endpoint.",
            action_required="Return JSON matching output_schema.",
            output_schema={"type": "object", "properties": {"x": {"type": "string"}}},
        )
        assert pi.current_phase == "plan"
        assert pi.is_terminal is False
        assert pi.retry_count == 0

    def test_empty_output_schema_raises(self):
        with pytest.raises(ValidationError, match="output_schema"):
            PhaseInstruction(
                session_id=SESSION,
                current_phase="plan",
                system_prompt="x",
                user_message="x",
                action_required="x",
                output_schema={},  # empty — should fail
            )

    def test_terminal_phase_complete(self):
        pi = PhaseInstruction(
            session_id=SESSION,
            current_phase="complete",
            system_prompt="",
            user_message="Done.",
            action_required="Notify user.",
            output_schema={"type": "object"},
            is_terminal=True,
        )
        assert pi.is_terminal is True

    def test_context_lessons_injected(self):
        pi = PhaseInstruction(
            session_id=SESSION,
            current_phase="implement",
            system_prompt="x",
            user_message="x",
            action_required="x",
            output_schema={"type": "object"},
            context={"lessons_learned": "Retry 1: use uuid7()"},
        )
        assert pi.context["lessons_learned"] == "Retry 1: use uuid7()"

    def test_output_schema_from_reviewer_output(self):
        schema = ReviewerOutput.model_json_schema()
        pi = PhaseInstruction(
            session_id=SESSION,
            current_phase="review_final",
            system_prompt="x",
            user_message="x",
            action_required="x",
            output_schema=schema,
        )
        assert "approved" in pi.output_schema.get("properties", {})

    def test_retry_count_defaults_to_zero(self):
        pi = PhaseInstruction(
            session_id=SESSION,
            current_phase="implement",
            system_prompt="x",
            user_message="x",
            action_required="x",
            output_schema={"type": "object"},
        )
        assert pi.retry_count == 0
