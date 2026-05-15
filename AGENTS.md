# AGENTS.md — baby-jasmine

Instructions for AI coding agents and humans working in this repo.

## Project

Minimal Pi-style agent CLI: **local stdin** and **WeCom** (optional extra), with **Tuya Ocean** or **Ollama** backends. Python **3.11+**, package layout under `src/baby_jasmine/`.

## Environment (uv)

Prefer **uv** over ad-hoc `pip`/`venv`:

```bash
# Install runtime + dev tools (pytest, ruff)
uv sync --extra dev

# WeCom WebSocket bot (adds git-based wecom-aibot, etc.)
uv sync --extra wecom --extra dev

# Run CLI
uv run baby-jasmine --local --project-root .

# Tests and lint
uv run pytest
uv run ruff check src tests
uv run ruff check --fix src tests   # when fixing I001 etc.
```

Repo includes `uv.lock`. After changing dependencies in `pyproject.toml`, run `uv lock` then `uv sync --extra dev`. Python version hint: `.python-version` (3.12).

## Layout

| Path | Role |
|------|------|
| `src/baby_jasmine/loop/` | Agent loop: `turn.py` (`run_turn`), `runner.py` |
| `src/baby_jasmine/context/` | System-prompt builder + post-processing (emoji cap / repair) |
| `src/baby_jasmine/memory/` | `SessionMemory` (in-proc), `JsonlHistory` (transcripts) |
| `src/baby_jasmine/tools/` | `Tool` protocol, `@tool` registry, `builtin/` |
| `src/baby_jasmine/llm/` | Driver + shared types (Anthropic-shaped `Message`) |
| `src/baby_jasmine/channels/` | `local.py`, `wecom.py` (transport) |
| `src/baby_jasmine/cli.py` | CLI entry + config/* loader |
| `config/agent.example.yaml` | Documented defaults; safe to edit in PRs |
| `config/agent.yaml` | Local / operator config (often gitignored or private — do not overwrite blindly) |
| `templates/*.md` | System prompt fragments (`identity`, `personality`, `skills`, `tools`) |
| `tests/` | `pytest`; `pythonpath` includes `src` via `pyproject.toml` |
| `data/transcripts/` | Runtime JSONL logs (default) |
| `docs/ARCHITECTURE.md` | Four-layer architecture explained |

## Config semantics (short)

- **`llm`**: global provider/model, then `llm.channels.local` / `llm.channels.wecom`, then per-WeCom-user overrides.
- **`reply`**: `max_emojis`, `repair.enabled` — post-process after each assistant turn (`context/post` + optional repair LLM call in `loop/turn`); `reply.channels.wecom.overrides.<userid>.force_assistant` (non-empty string) skips generation and returns that text for that user.
- **Sections** (`personality`, `skills`, `tools`): can be toggled per channel / per WeCom user; WeCom `overrides.<userid>` may set `enabled` and/or `template` (per-user markdown). For `personality` only, `template_merge: append` appends the per-user file to the default `template` instead of replacing it.
- **Tools**: built-in tools auto-register on startup (`tools/builtin/__init__.py`). Add your own via `@tool(...)` in `tools/builtin/` and add one import line.

## Conventions for changes

- Match existing style; **ruff** enforces E/F/I/UP, line length 100.
- Keep edits **surgical**: touch only files needed for the task.
- Add or update **tests** for new behavior (`tests/`).
- Do not commit secrets; use `.env` or env vars (see `README.md`).

## Docs

- Operator-facing setup and env vars: [README.md](README.md).
- Four-layer architecture (loop / context / memory / tools): [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
