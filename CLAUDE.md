# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install
uv sync --extra dev                  # runtime + pytest + ruff
uv sync --extra wecom --extra dev    # + WeCom WebSocket SDK

# Run
uv run baby-jasmine --local --project-root .
uv run baby-jasmine --wecom --project-root .
uv run baby-jasmine --local --provider ollama --model llama3.2

# Test and lint
uv run pytest
uv run pytest tests/test_config_loader.py   # single file
uv run ruff check src tests
uv run ruff check --fix src tests           # auto-fix import order etc.
uv run ruff format src tests

# After changing pyproject.toml dependencies
uv lock && uv sync --extra dev
```

Config: copy `config/agent.example.yaml` → `config/agent.yaml` and set env vars (`OCEAN_SCENE_ID`, `WECOM_BOT_ID`, `WECOM_BOT_SECRET`, etc.) in `.env`.

## Architecture

The agent is organized into four layers:

| Layer | Path | Role |
|-------|------|------|
| **Loop** | `loop/turn.py`, `loop/runner.py` | Single-turn orchestration: build context → call LLM → execute tools → repeat → post-process |
| **Context** | `context/builder.py`, `context/post.py` | Assemble system prompt from templates + skills; emoji cap + optional repair pass |
| **Memory** | `memory/transcripts.py`, `memory/context.py`, `memory/person_store.py` | `JsonlHistory` (JSONL on disk); `AgentSessionManager` wires cold history into `pi-agent-core` `Agent` objects |
| **Tools** | `tools/registry.py`, `tools/builtin/` | `@tool` decorator registers functions; `list_tools()` returns schemas for the model each turn |

**LLM drivers** (`pi_stream/ocean.py`, `pi_stream/ollama.py`) are translators, not a layer — they convert between the internal Anthropic-shaped messages and provider wire formats. `factory.py` selects the driver from `ResolvedLlmConfig`.

**`AgentSessionManager`** (`agent_sessions.py`) caches one `pi-agent-core` `Agent` per `session_key`. Cold sessions are hydrated from `JsonlHistory.load_recent_messages()` — only text turns replay; tool calls do not.

**Channels** (`channels/local.py`, `channels/wecom.py`) are transport wrappers. They read messages and call `run_turn(...)` — the loop is channel-agnostic.

## Key extension points

**Add a tool** — one file in `tools/builtin/`, one import in `tools/builtin/__init__.py`. Use `@tool(name, description, input_schema)`.

**Add a channel** — implement `async def run_<name>_loop(cfg, project_root, history, memory, cli_provider, cli_model)` and wire the CLI flag in `cli.py` + `loop/runner.py`. See `channels/wecom.py`.

**Add a provider** — implement a `stream_fn` (Anthropic-shaped in, events + result out) and register it in `pi_stream/factory.py`. OpenAI-shaped providers need translation like `ollama.py`.

**Add a skill** — drop a folder `skills/<name>/SKILL.md`. Skills are auto-discovered; the content is injected into the system prompt as `<skill name="...">` blocks.

## Config hierarchy

LLM resolution order (most-specific wins): CLI flags → per-WeCom-user override → channel default (`llm.channels.local` / `llm.channels.wecom`) → global `llm`.

System-prompt sections (`personality`, `skills`, `tools`): each section can be toggled per-channel and per-WeCom-user. For `personality`, `template_merge: append` appends the per-user file instead of replacing the default. See `config/agent.example.yaml` for the full schema.

`reply.repair.enabled: true` triggers a second LLM call after the first draft if emoji count exceeds `max_emojis`. `force_assistant` on a WeCom user override skips generation entirely.

## Conventions

- Linter: **ruff** (E/F/I/UP, line length 100, target Python 3.11). Run before committing.
- Tests live in `tests/`; `src/` is on `pythonpath` via `pyproject.toml`.
- Transcripts are append-only JSONL at `data/transcripts/{YYYY-MM}/{YYYY-MM-DD}.jsonl`.
- `config/agent.yaml` is operator config — do not overwrite blindly; `config/agent.example.yaml` is the safe-to-edit reference.
- Internal message shape is Anthropic Messages throughout; `pi-agent-core` types (`Model`, `Agent`, `TextContent`, etc.) are the canonical in-process types.
