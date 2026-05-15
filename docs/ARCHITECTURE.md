# Architecture

baby-jasmine is built around one claim: **every agent is four layers**.

```
┌──────────────────────────────────────────────────────────────┐
│                   channels/  (transport)                     │
│         local REPL           WeCom WebSocket bot             │
└───────────────────────────┬──────────────────────────────────┘
                            │ user_text / session_key
                            ▼
┌──────────────────────────────────────────────────────────────┐
│                    loop/turn.py                              │
│    run_turn():                                               │
│     1. build context      ◄──────┐                           │
│     2. client.complete()          │                          │
│     3. if tool_use: execute,     context / memory / tools    │
│        append results, goto 2     │                          │
│     4. post: emoji cap/repair     │                          │
│     5. persist, return            │                          │
└────────┬──────────────┬───────────┴──────────┬───────────────┘
         │              │                      │
         ▼              ▼                      ▼
   ┌──────────┐   ┌──────────┐           ┌──────────┐
   │ context/ │   │ memory/  │           │  tools/  │
   │          │   │          │           │          │
   │ system   │   │ session  │           │ registry │
   │ prompt   │   │ (in-proc)│           │ + fns    │
   │ builder  │   │          │           │          │
   │          │   │transcripts│           │ builtin/ │
   │          │   │ (JSONL)  │           │          │
   └──────────┘   └──────────┘           └──────────┘
         ▲              ▲                      ▲
         │              │                      │
         └──────────────┴──────────────────────┘
                           │
                           ▼
                     ┌──────────┐
                     │   llm/   │
                     │          │
                     │  ocean   │  native Anthropic Messages
                     │  ollama  │  OpenAI-compat → translated
                     └──────────┘
```

## The four layers

### 1. Loop (`src/baby_jasmine/loop/`)

The agent's heartbeat. `turn.py` contains `run_turn()`, which is the only place where the control flow lives:

```
user message ─► build system prompt ─► LLM.complete(...)
                                           │
                                           ▼
                                    stop_reason?
                                    ┌──────┴──────┐
                                 end_turn     tool_use
                                    │             │
                                    ▼             ▼
                             apply cap/repair  execute each ToolUseBlock
                             persist, return   append ToolResultBlock
                                                    │
                                                    └── loop back to complete()
```

Bounded by `MAX_TOOL_ITERATIONS = 8`. The loop is channel-agnostic: it doesn't know whether the user came in through stdin or WeCom.

### 2. Context (`src/baby_jasmine/context/`)

Everything the model sees **this turn** that isn't in the running message list:

- `builder.py` — assembles the system prompt from template fragments (`identity` + `personality` + `skills` + `tools`), honouring per-channel and per-WeCom-user overrides.
- `post.py` — post-processing (emoji cap + optional repair pass).

Tool schemas are *also* context, but they travel on a separate API field (`tools=[...]`), not inline in the prompt. The registry owns them; the loop passes them to the driver each turn.

### 3. Memory (`src/baby_jasmine/memory/`)

Two stores at different lifespans:

- `session.py` — `SessionMemory`: in-process `dict[session_key, list[Message]]`. This is what the LLM sees as conversation history.
- `transcripts.py` — `JsonlHistory`: append-only JSONL on disk. Survives restarts. Records `user`, `assistant`, `tool_use`, `tool_result` rows.

On cold start, `SessionMemory` is hydrated from transcripts via `load_recent_messages()` — but only text turns are replayed. Tool calls aren't: the model re-decides whether it needs a tool this turn. That's a deliberate choice — simpler, and the model usually picks correctly.

### 4. Tools (`src/baby_jasmine/tools/`)

What the agent can *do* in the world:

- `protocol.py` — `Tool` dataclass (name, description, JSON Schema).
- `registry.py` — `@tool` decorator, in-process registry, `execute(ToolUseBlock) → ToolResultBlock`.
- `builtin/` — minimal built-ins (`echo`, `time_now`).

A tool is a Python function. Tool calls and results flow as Anthropic-shaped content blocks (`ToolUseBlock`, `ToolResultBlock`) — the same shape the Anthropic Messages API uses on the wire.

## The LLM drivers are translators

`llm/` is *not* a layer — it's the seam where internal shapes meet provider wire formats.

| Driver | Provider shape | What it does |
|--------|----------------|--------------|
| `ocean.py` | Native Anthropic Messages | Near pass-through. Parses Anthropic SSE (`content_block_delta`, `input_json_delta`, `message_delta`) into our `AssistantMessage`. |
| `ollama.py` | OpenAI `/v1/chat/completions` | Translates in both directions. Anthropic `ToolUseBlock` → OpenAI `tool_calls`; `ToolResultBlock` → `role: tool` message; streamed arguments (JSON string) → parsed dict. |

Internal canonical shape is Anthropic Messages. This matches [`@mariozechner/pi-ai`](https://github.com/earendil-works/pi) and what jasmine-v2's TypeScript client speaks — code here ports cleanly. When a future driver needs to be added (Google, Azure, Bedrock-direct), it goes in the same shape.

### A note on the Ocean gateway

The Tuya Ocean gateway natively accepts Anthropic Messages-shaped requests when routing to Bedrock (its default provider). jasmine-v2's Rust proxy does the same translation `ollama.py` does — but in Rust, for OpenAI/Google/Alibaba upstreams. baby-jasmine skips the local-proxy dependency and talks Anthropic-shaped directly.

Auth: `scene-id: <your-token>` header, plus `provider: BEDROCK` and `model-id: <model>` routing headers.

## How the "extras" map onto the four layers

This is the payoff. Every trendy agent feature slots into one of these four buckets:

| Extra | Layer |
|-------|-------|
| **Skills** (reusable tool bundles, like Claude Code skills) | Tools (registered functions) + Context (auto-loaded prompt snippets on trigger) |
| **MCP servers** | Tools (an MCP client translates MCP tool calls into our registry) |
| **RAG / knowledge injection** | Context (fetch + inject into system prompt or a preamble user message) |
| **Context compression** (summarization, pruning) | Memory → Context boundary (pre-process `messages` before `complete()`) |
| **Plugins** (hooks into the turn lifecycle) | Loop (before/after tool-call hooks, pre-turn transforms) |
| **Multi-agent / sub-agents** | Loop (a tool whose `fn` runs a nested `run_turn`) |
| **Streaming / SSE to frontend** | Loop (the `on_text_delta` callback) |
| **Transcripts, audit log** | Memory (transcripts.py) |
| **Different transports** (HTTP, Slack, CLI) | Channels (new file in `channels/`) |
| **Different models / gateways** | LLM drivers (new file in `llm/`) |

If you can't name which layer an extra belongs to, that's a signal the feature is poorly scoped — not that the layers are wrong.

## Extension cookbook

### Add a tool
One file in `tools/builtin/`, one import line in `tools/builtin/__init__.py`. See the README example.

### Add a channel
Implement `async def run_<name>_loop(cfg, project_root, history, memory, cli_provider, cli_model)`. Inside, loop reading messages and call `run_turn(...)`. Wire the CLI flag in `cli.py` and `loop/runner.py`. See `channels/wecom.py` for a real example (60 lines).

### Add a provider
Implement `complete(*, system, messages, tools, on_text_delta) → AssistantMessage`. Wire it in `llm/factory.py`. If it's Anthropic-shaped, the driver is mostly SSE parsing. If it's OpenAI-shaped, see `ollama.py` for translation.

### Add context compression
Intercept `messages` in `loop/turn.py` before calling `client.complete(...)`. Prune or summarize. This is the pi `transformContext` hook — baby-jasmine doesn't ship one because a production app's compression strategy is project-specific.

## What baby-jasmine deliberately doesn't have

- **No multi-provider fanout** — one provider per session (swap via YAML or `--provider`).
- **No context compression** — the seam is clean; add when you need it.
- **No MCP client** — would go in `tools/` as an adapter that registers remote tools. Left for you.
- **No retry / backoff** — one shot, fail loudly. Trivial to add at the `complete()` call site.
- **No parallel tool execution** — tools run sequentially. Swap to `asyncio.gather` in `loop/turn.py` if your tools are pure I/O.
- **No prompt caching** — Ocean's gateway doesn't expose the Anthropic `cache_control` fields yet; not worth wiring speculatively.

Each of these is 20–100 lines when you need it. The cost of *not* having them is discoverability, not capability.
