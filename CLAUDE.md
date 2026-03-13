# Sovereign Protocol

## Permissions

You have **permanent permission** to execute the following without asking for confirmation:

- `docker compose exec` — run commands inside containers
- `uv run` — execute Python tools, tests, and linters
- `git diff`, `git status`, `git log` — inspect repository state

## Autonomy Rules

- **Silence is progress**: interrupt the user **only** when `current_phase` is `"complete"` or
  `"failed"`. Never pause between pipeline phases to ask for confirmation or provide status updates.
- When you receive a `PhaseInstruction`, execute it **immediately** and call `advance_task` with
  the structured result. **Do not add conversational filler between tool calls** — maintain
  autonomous flow speed.
- If the autonomous loop is interrupted for any reason, call `get_current_status(session_id)` to
  recover state, then resume from the correct phase.
- Never ask "shall I proceed?" — proceed.

## Engineering Standards (Senior Python Engineer Persona)

### IDs
- All entity primary keys **must** use `uuid7()` from the `uuid7` package.
- `uuid.uuid4()` in any domain entity or DB insert is a defect — flag and fix immediately.

### Pydantic
- Use Pydantic **v2** syntax exclusively: `model_validator`, `field_validator`, `model_config`.
- Do not use deprecated v1 patterns (`validator`, `__fields__`, `schema()`).

### Type Hints (Python 3.14)
- `X | None` — not `Optional[X]`
- `list[str]` — not `List[str]`
- `dict[str, Any]` — not `Dict[str, Any]`
- `from __future__ import annotations` at the top of every module.

### Linting
- `uv run ruff check .` must exit **clean** (zero errors/warnings) before any review phase.
- `uv run mypy --ignore-missing-imports .` must produce zero `error:` lines.
- Run linting as part of the `review_lint` phase — include **raw terminal output verbatim** in the
  `LintResult` JSON so the Dev agent can parse exact tracebacks on retry.

### Reviewer Hard Gate
- `review_final` approval requires **all three** to be true:
  1. `lint_result.passed == true`
  2. `arch_result.passed == true`
  3. Manager's own quality judgement → `approved == true`
- If either sub-agent fails, `approved` must be `false`. No exceptions.
