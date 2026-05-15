# baby-jasmine

A minimal, production-lean agent in ~1500 lines of Python — built to show how to build your own Claude Code / openclaw-style agent from first principles.

**Thesis**: every agent, no matter how big, is four layers.

| Layer | What it does | Where it lives |
|-------|--------------|----------------|
| **Loop** | Drives the turn; calls the model, dispatches tools, decides when to stop. | `src/baby_jasmine/loop/` |
| **Context** | Assembles what the model sees *this turn* (system prompt + tool schemas). | `src/baby_jasmine/context/` |
| **Memory** | What survives across turns and sessions (in-proc timeline + JSONL transcripts). | `src/baby_jasmine/memory/` |
| **Tools** | What the agent can actually *do* in the world (registered Python functions). | `src/baby_jasmine/tools/` |

Everything else is a plug-in on top. Channels (`local`, `wecom`) are transport. LLM drivers (`ocean`, `ollama`) are translators. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## What's in the box

- **Local REPL** and **WeCom bot** (企业微信智能机器人), sharing the same loop.
- **Tuya Ocean gateway** (native Anthropic Messages format) and **Ollama** (OpenAI-compat) drivers.
- **Pi-compatible internal shapes** — message types mirror [`@mariozechner/pi-ai`](https://github.com/earendil-works/pi) so code here lifts cleanly to that ecosystem.
- **Tool-calling**: register a Python function with `@tool`; the model can call it.
- **Pluggable personality** per WeCom user (template files, emoji budget, force-assistant override).

## Setup

```bash
uv sync --extra dev                  # basic install
uv sync --extra wecom --extra dev    # + WeCom WebSocket SDK
cp config/agent.example.yaml config/agent.yaml
```

Environment (put in `.env` or export):

| Variable | Used for |
|----------|----------|
| `OCEAN_GATEWAY_URL` | Defaults to the Tuya gateway if unset |
| `OCEAN_SCENE_ID` | Ocean auth token (sent as `scene-id` header) |
| `OLLAMA_BASE_URL` or `OLLAMA_HOST` | Local Ollama OpenAI-compat endpoint |
| `WECOM_BOT_ID` / `WECOM_BOT_SECRET` | WeCom bot credentials |

## Run

```bash
# Local REPL
uv run baby-jasmine --local --project-root .

# WeCom bot (needs [wecom] extra + env vars)
uv run baby-jasmine --wecom --project-root .

# Both in parallel
uv run baby-jasmine --all --project-root .

# Override provider/model for this process
uv run baby-jasmine --local --provider ollama --model llama3.2
```

## Add a tool in 10 lines

```python
# src/baby_jasmine/tools/builtin/weather.py
from baby_jasmine.tools.registry import tool

@tool(
    name="weather",
    description="Return the current weather for a city.",
    input_schema={
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
    },
)
def weather(args: dict) -> str:
    return f"It is sunny in {args['city']}."
```

Import it once (e.g. add to `tools/builtin/__init__.py`) and the model can call it.

## Tests

```bash
uv run pytest
uv run ruff check src tests
```

## Notes

- Transcripts: append-only JSONL under `data/transcripts/{YYYY-MM}/{YYYY-MM-DD}.jsonl`. Contains user / assistant / `tool_use` / `tool_result` rows.
- Ocean requests go direct to the gateway (no local proxy dependency). The driver reproduces the same translation that jasmine-v2's Rust proxy does when routing OpenAI-style upstreams, but for the default Bedrock/Anthropic path it's a pass-through.
- If the gateway returns Bedrock binary `amazon.eventstream`, streaming isn't supported — the client raises a clear error.
- For AI contributors: [AGENTS.md](AGENTS.md).
