# Sovereign Engineering Office — Local Multi-Agent Brain

A local Multi-Agent Brain built with **FastMCP** and **Pydantic AI**, orchestrating four specialized agents following the **Canon TDD** workflow.  No external API calls — every tool returns a structured `AgentInstruction` that **you (Claude CLI)** execute using your Teams subscription.

---

## Architecture

```
Claude CLI (Teams subscription)
        │
        │  MCP/SSE
        ▼
┌──────────────────────────────────────────┐
│         Sovereign Brain (FastMCP)        │
│                                          │
│  Tool: start_session   → Architect       │
│  Tool: get_test_spec   → Tester          │
│  Tool: implement_logic → Dev             │
│  Tool: run_review      → Reviewer        │
│  Tool: fetch_context   → PostgreSQL 18   │
└──────────────────────────┬───────────────┘
                           │
                    ┌──────▼──────┐
                    │ PostgreSQL  │
                    │     18      │
                    │  sessions   │
                    │  context    │
                    └─────────────┘
```

### The Four Agents

| Agent | Phase | Role |
|-------|-------|------|
| **Architect** | Plan | Structural design, DDD/UUIDv7 enforcement, implementation phases |
| **Tester** | Red | Writes failing tests before any production code |
| **Dev** | Green | Minimal code to make the failing tests pass |
| **Reviewer** | Gate | Final quality + "vibe" compliance check (score 1-10) |

### Canonical Workflow

```
start_session(request)           ← Architect produces plan
    ↓
get_test_spec(plan)              ← Tester writes failing test (Red)
    ↓
[You write test file → confirm it fails]
    ↓
implement_logic(test_results)    ← Dev writes minimal code (Green)
    ↓
[You write code file → run tests → if fail, retry with error_output]
    ↓
run_review(diff)                 ← Reviewer gates quality (vibe ≥ 6)
    ↓
If rejected → start_session(review_feedback=...) to iterate
```

---

## Quick Start

### 1. Prerequisites

- [uv](https://docs.astral.sh/uv/) ≥ 0.5
- Docker + Docker Compose
- [golang-migrate](https://github.com/golang-migrate/migrate) (for local migrations)

### 2. Install

```bash
cp .env.example .env
uv sync
```

### 3. Start Infrastructure

```bash
# Start PostgreSQL 18
just up postgres

# Apply migrations
just migrate-up

# Start MCP server locally
just dev
```

Or run everything in Docker:

```bash
just up
just migrate      # runs migrate container
```

### 4. Connect Claude CLI

Add to your `.mcp.json` (already present in the repo root):

```json
{
  "mcpServers": {
    "sovereign-brain": {
      "type": "sse",
      "url": "http://localhost:8000/sse"
    }
  }
}
```

Restart Claude CLI — the five tools will appear automatically.

---

## MCP Tools

### `start_session(request, project_context?, review_feedback?)`

Triggers the **Architect** agent. Returns an `AgentInstruction` with a full system prompt + user message.

- Creates a session in PostgreSQL (UUIDv7 session ID)
- Returns `session_id` — **keep this for all subsequent calls**

### `get_test_spec(plan, session_id, scenario?, existing_code?, project_context?)`

Triggers the **Tester** agent (Red phase). Write the test file to disk and confirm it fails.

### `implement_logic(test_code, test_file_path, session_id, error_output?, existing_code?)`

Triggers the **Dev** agent (Green phase). Write the implementation file. If tests still fail, call again with `error_output` (up to 3 retries).

### `run_review(diff, session_id, changed_files?, plan?, project_context?)`

Triggers the **Reviewer** agent. Returns `approved` (bool), `vibe_score` (1-10), and `required_changes`. If rejected, iterate from `start_session` with `review_feedback`.

### `fetch_context(query, session_id?, limit?)`

Queries PostgreSQL history. Use to find prior architectural decisions, patterns, and implementations.

---

## Database Schema

```sql
-- All IDs: UUIDv7 (timestamp-ordered)

sessions (
    id UUID PK,          -- UUIDv7
    request TEXT,        -- original request
    plan JSONB,          -- Architect output
    test_spec JSONB,     -- Tester output
    implementation JSONB,-- Dev output
    review JSONB,        -- Reviewer output
    status VARCHAR(20),  -- active|testing|implementing|reviewing|approved|rejected
    created_at, updated_at TIMESTAMPTZ
)

context_history (
    id UUID PK,          -- UUIDv7
    session_id UUID FK,
    event_type VARCHAR(50), -- plan|test|implement|review|feedback
    data JSONB,
    summary TEXT,        -- full-text searchable
    created_at TIMESTAMPTZ
)
```

---

## Development

```bash
just test            # run all tests
just lint            # check style
just lint-fix        # auto-fix
just migrate-create name=add_feature  # new migration
```

---

## Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.14 |
| Package manager | uv |
| Agent framework | Pydantic AI |
| MCP server | FastMCP 2.x |
| Database | PostgreSQL 18 |
| DB driver | asyncpg |
| Migrations | golang-migrate |
| Container | Docker Compose |
