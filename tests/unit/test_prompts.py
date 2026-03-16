"""Unit tests for prompt loading."""

import pytest

from sovereign_brain.agents.base import load_prompt

AGENT_NAMES = ["architect", "tester", "dev", "reviewer", "lint_agent", "architecture_agent"]


@pytest.mark.parametrize("agent_name", AGENT_NAMES)
def test_prompt_loads_successfully(agent_name):
    prompt = load_prompt(agent_name)
    assert isinstance(prompt, str)
    assert len(prompt) > 50


@pytest.mark.parametrize("agent_name", AGENT_NAMES)
def test_prompt_is_not_empty(agent_name):
    prompt = load_prompt(agent_name)
    assert prompt.strip() != ""


def test_architect_prompt_mentions_ddd():
    prompt = load_prompt("architect")
    assert "DDD" in prompt or "Domain" in prompt or "domain" in prompt


def test_architect_prompt_mentions_uuidv7():
    prompt = load_prompt("architect")
    assert "UUIDv7" in prompt or "uuid7" in prompt or "UUID" in prompt


def test_tester_prompt_mentions_red_phase():
    prompt = load_prompt("tester")
    assert "Red" in prompt or "failing" in prompt or "fail" in prompt


def test_dev_prompt_mentions_green_phase():
    prompt = load_prompt("dev")
    assert "Green" in prompt or "minimal" in prompt or "minimum" in prompt


def test_reviewer_prompt_mentions_vibe():
    prompt = load_prompt("reviewer")
    assert "vibe" in prompt.lower()


def test_lint_agent_prompt_mentions_ruff():
    prompt = load_prompt("lint_agent")
    assert "ruff" in prompt.lower()


def test_lint_agent_prompt_mentions_raw_output():
    prompt = load_prompt("lint_agent")
    assert "raw" in prompt.lower() or "verbatim" in prompt.lower()


def test_lint_agent_prompt_mentions_mypy():
    prompt = load_prompt("lint_agent")
    assert "mypy" in prompt.lower()


def test_architecture_agent_prompt_mentions_solid():
    prompt = load_prompt("architecture_agent")
    assert "SOLID" in prompt or "solid" in prompt.lower()


def test_architecture_agent_prompt_mentions_ddd():
    prompt = load_prompt("architecture_agent")
    assert "DDD" in prompt or "domain" in prompt.lower()


def test_architecture_agent_prompt_mentions_uuidv7():
    prompt = load_prompt("architecture_agent")
    assert "UUIDv7" in prompt or "uuid7" in prompt
