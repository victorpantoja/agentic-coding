"""Unit tests for pure orchestrator helper functions."""

from __future__ import annotations

import json

import sovereign_brain.agents.orchestrator as orch


class TestSummariseLessons:
    def test_empty_history_returns_empty_string(self):
        assert orch._summarise_lessons([]) == ""

    def test_single_row_includes_iteration_and_lesson(self):
        history = [{"iteration": 1, "lessons_learned": "Used uuid4 instead of uuid7"}]
        result = orch._summarise_lessons(history)
        assert "Retry 1" in result
        assert "uuid4" in result

    def test_multiple_rows_joined_by_pipe(self):
        history = [
            {"iteration": 1, "lessons_learned": "Lesson A"},
            {"iteration": 2, "lessons_learned": "Lesson B"},
        ]
        result = orch._summarise_lessons(history)
        assert "Retry 1" in result
        assert "Retry 2" in result
        assert "|" in result

    def test_long_lesson_truncated_to_120_chars(self):
        long_lesson = "x" * 200
        history = [{"iteration": 1, "lessons_learned": long_lesson}]
        result = orch._summarise_lessons(history)
        # should be truncated — full 200 chars should NOT appear
        assert long_lesson not in result

    def test_falls_back_to_reviewer_critique(self):
        history = [{"iteration": 1, "lessons_learned": "", "reviewer_critique": "Critique text"}]
        result = orch._summarise_lessons(history)
        assert "Critique text" in result

    def test_row_without_lesson_or_critique_skipped(self):
        history = [{"iteration": 1, "lessons_learned": "", "reviewer_critique": ""}]
        result = orch._summarise_lessons(history)
        assert result == ""


class TestOneLinerCritique:
    def test_lint_failure_mentioned(self):
        result = orch._one_liner_critique("some critique", 1, lint_passed=False, arch_passed=True)
        assert "lint failed" in result

    def test_arch_failure_mentioned(self):
        result = orch._one_liner_critique("some critique", 2, lint_passed=True, arch_passed=False)
        assert "architecture violations" in result

    def test_both_failures_mentioned(self):
        result = orch._one_liner_critique("x", 1, lint_passed=False, arch_passed=False)
        assert "lint failed" in result
        assert "architecture violations" in result

    def test_iteration_number_in_result(self):
        result = orch._one_liner_critique("x", 3, lint_passed=True, arch_passed=True)
        assert "3" in result

    def test_first_line_of_critique_included(self):
        result = orch._one_liner_critique(
            "Line one of critique\nLine two", 1, lint_passed=True, arch_passed=True
        )
        assert "Line one of critique" in result

    def test_manager_rejected_fallback(self):
        result = orch._one_liner_critique("", 1, lint_passed=True, arch_passed=True)
        assert "manager rejected" in result or "review rejected" in result


class TestFirstScenario:
    def test_uses_first_implementation_phase(self):
        plan = {"implementation_phases": ["Create UserService", "Add endpoints"]}
        result = orch._first_scenario(plan)
        assert "Create UserService" in result

    def test_falls_back_to_first_component_name(self):
        plan = {"components": [{"name": "HealthController", "purpose": "Returns 200"}]}
        result = orch._first_scenario(plan)
        assert "HealthController" in result

    def test_handles_string_component(self):
        plan = {"components": ["SimpleService"]}
        result = orch._first_scenario(plan)
        assert "SimpleService" in result

    def test_returns_default_when_plan_empty(self):
        result = orch._first_scenario({})
        assert isinstance(result, str)
        assert len(result) > 0


class TestDeriveCurrentPhase:
    def _make_steps(self, statuses: dict[str, str]) -> list[dict]:
        names = ["plan", "test", "implement", "review"]
        return [{"step_name": n, "status": statuses.get(n, "pending")} for n in names]

    def test_plan_running_returns_plan(self):
        steps = self._make_steps({"plan": "running"})
        assert orch._derive_current_phase(steps, {}) == "plan"

    def test_test_running_returns_test(self):
        steps = self._make_steps({"plan": "finished", "test": "running"})
        assert orch._derive_current_phase(steps, {}) == "test"

    def test_implement_running_returns_implement(self):
        steps = self._make_steps({"plan": "finished", "test": "finished", "implement": "running"})
        assert orch._derive_current_phase(steps, {}) == "implement"

    def test_review_running_returns_review_lint(self):
        steps = self._make_steps(
            {"plan": "finished", "test": "finished", "implement": "finished", "review": "running"}
        )
        assert orch._derive_current_phase(steps, {}) == "review_lint"

    def test_review_finished_approved_returns_complete(self):
        steps = self._make_steps(
            {"plan": "finished", "test": "finished", "implement": "finished", "review": "finished"}
        )
        assert orch._derive_current_phase(steps, {"status": "approved"}) == "complete"

    def test_review_finished_rejected_returns_failed(self):
        steps = self._make_steps(
            {"plan": "finished", "test": "finished", "implement": "finished", "review": "finished"}
        )
        assert orch._derive_current_phase(steps, {"status": "rejected"}) == "failed"


_LINT_CLEAN = {"passed": True, "issues": [], "raw_ruff_output": "", "raw_mypy_output": ""}
_LINT_FAIL = {"passed": False, "issues": ["old"], "raw_ruff_output": "old", "raw_mypy_output": ""}
_ARCH_PASS = {"passed": True, "violations": [], "notes": "", "raw_analysis": ""}
_ARCH_FAIL = {"passed": False, "violations": ["x"], "notes": "", "raw_analysis": ""}


class TestExtractSubAgentResult:
    def test_extracts_review_lint_from_events(self):
        events = [{"data": {"review_lint": _LINT_CLEAN}}]
        result = orch._extract_sub_agent_result(events, "review_lint")
        assert result["passed"] is True

    def test_returns_latest_when_multiple_events(self):
        events = [
            {"data": {"review_lint": _LINT_FAIL}},
            {"data": {"review_lint": _LINT_CLEAN}},
        ]
        # reversed() should pick the last one
        result = orch._extract_sub_agent_result(events, "review_lint")
        assert result["passed"] is True

    def test_returns_empty_dict_when_not_found(self):
        events = [{"data": {"review_arch": _ARCH_PASS}}]
        result = orch._extract_sub_agent_result(events, "review_lint")
        assert result == {}

    def test_handles_string_data_json(self):
        events = [{"data": json.dumps({"review_arch": _ARCH_FAIL})}]
        result = orch._extract_sub_agent_result(events, "review_arch")
        assert result["passed"] is False


# ── Regression: bug fixes ─────────────────────────────────────────────────────


class TestJsonField:
    """
    Regression tests for _json_field().

    Bug: asyncpg returns JSONB columns as raw JSON strings, not dicts.
    ReviewerInput(plan=...) raised ValidationError when given a string.
    Fix: _json_field() decodes strings via json.loads before use.
    """

    def test_returns_dict_unchanged(self):
        session = {"plan": {"components": [], "architecture_plan": "x"}}
        result = orch._json_field(session, "plan")
        assert result == {"components": [], "architecture_plan": "x"}

    def test_decodes_json_string_to_dict(self):
        """Core regression: asyncpg JSONB → string must be decoded."""
        raw = json.dumps({"components": [{"name": "Svc"}], "architecture_plan": "y"})
        session = {"plan": raw}
        result = orch._json_field(session, "plan")
        assert isinstance(result, dict)
        assert result["architecture_plan"] == "y"

    def test_decoded_dict_is_valid_for_reviewer_input(self):
        """Decoded plan must not raise ValidationError when passed to ReviewerInput."""
        from sovereign_brain.agents.base import ReviewerInput

        raw = json.dumps({"components": [], "architecture_plan": "test plan"})
        session = {"plan": raw}
        plan = orch._json_field(session, "plan")
        # Must not raise
        ri = ReviewerInput(diff="+x", plan=plan)
        assert ri.plan["architecture_plan"] == "test plan"

    def test_missing_key_returns_empty_dict(self):
        assert orch._json_field({}, "plan") == {}

    def test_none_value_returns_empty_dict(self):
        assert orch._json_field({"plan": None}, "plan") == {}

    def test_empty_string_returns_empty_dict(self):
        assert orch._json_field({"plan": ""}, "plan") == {}

    def test_invalid_json_string_returns_empty_dict(self):
        assert orch._json_field({"plan": "not-valid-json{"}, "plan") == {}

    def test_works_for_test_spec_field(self):
        raw = json.dumps({"test_code": "def test_x(): pass", "test_file_path": "t.py"})
        session = {"test_spec": raw}
        result = orch._json_field(session, "test_spec")
        assert result["test_file_path"] == "t.py"

    def test_works_for_implementation_field(self):
        raw = json.dumps({"code": "def foo(): pass", "file_path": "src/foo.py"})
        session = {"implementation": raw}
        result = orch._json_field(session, "implementation")
        assert result["file_path"] == "src/foo.py"


class TestTaskHistoryLoggedOnApproval:
    """
    Regression tests for the task_history always-empty bug.

    Bug: log_task_history was only called in the rejection branch of
    _handle_review_final. A first-pass approval produced zero rows.
    Fix: log_task_history is called before the approved/rejected branch
    with is_approved reflecting the actual outcome.
    """

    def test_log_task_history_signature_accepts_is_approved_true(self):
        """
        Verify queries.log_task_history accepts is_approved=True.
        This ensures the approval path can write a row without error.
        The actual DB write is covered by integration tests; here we
        confirm the call signature is correct.
        """
        import inspect

        from sovereign_brain.db import queries

        sig = inspect.signature(queries.log_task_history)
        params = sig.parameters
        assert "is_approved" in params
        # Default is False — the fix overrides it with the actual outcome
        assert params["is_approved"].default is False

    def test_handle_review_final_calls_log_before_approval_branch(self):
        """
        Structural test: ensure log_task_history appears in the source of
        _handle_review_final before the 'if effective_approved' return.
        This guards against the regression being reintroduced.
        """
        import inspect

        src = inspect.getsource(orch._handle_review_final)
        log_pos = src.index("log_task_history")
        approved_return_pos = src.index("current_phase=\"complete\"")
        assert log_pos < approved_return_pos, (
            "log_task_history must be called before the approved return path"
        )
