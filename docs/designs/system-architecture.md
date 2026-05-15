# Baby-Jasmine System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Baby-Jasmine AI Agent                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  INPUT CHANNELS                                                             │
│  ┌─────────────────────┐    ┌─────────────────────────┐                   │
│  │   Local Channel     │    │    WeCom Channel         │                   │
│  │  channels/local.py  │    │  channels/wecom.py       │                   │
│  │  stdin/stdout REPL  │    │  WebSocket bot (企业微信) │                   │
│  │  session: "local"   │    │  session: "wecom:{uid}"  │                   │
│  └──────────┬──────────┘    └────────────┬────────────┘                   │
│             └───────────────┬────────────┘                                 │
│                             ▼                                               │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │  LAYER 1 — LOOP   (loop/turn.py, loop/runner.py)                     │  │
│  │                                                                      │  │
│  │  run_turn()                                                          │  │
│  │    1. create_stream_fn() ─────────────► pi_stream/ adapters         │  │
│  │    2. build_system_prompt() ──────────► Context layer               │  │
│  │    3. list_tools() ───────────────────► Tools layer                 │  │
│  │    4. AgentSessionManager.get_or_create()                           │  │
│  │    5. agent.prompt() ─────────────────► pi-agent-core Agent         │  │
│  │         └─ tool loop handled internally by pi-agent-core            │  │
│  │    6. cap_emojis() / optional repair pass (direct StreamFn call)    │  │
│  │    7. Persist turn ───────────────────► Memory layer                │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│             │                    │                    │                     │
│             ▼                    ▼                    ▼                     │
│  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐           │
│  │ LAYER 2 — CONTEXT│ │ LAYER 3 — MEMORY │ │ LAYER 4 — TOOLS  │           │
│  │ context/builder  │ │                  │ │                  │           │
│  │ context/post.py  │ │ AgentSessionMgr  │ │ tools/registry   │           │
│  │                  │ │ (one Agent/sess) │ │ @tool decorator  │           │
│  │ Assembles system │ │       ↕          │ │ → AgentTool      │           │
│  │ prompt from:     │ │ JsonlHistory     │ │                  │           │
│  │ • identity.md    │ │ (disk JSONL)     │ │ Built-ins:       │           │
│  │ • personality.md │ │ data/transcripts │ │ • echo           │           │
│  │ • skills.md      │ │ /{YYYY-MM}/      │ │ • time_now       │           │
│  │ • tools.md       │ │ {YYYY-MM-DD}     │ │                  │           │
│  │                  │ │ .jsonl           │ │ Custom tools     │           │
│  │ Per-channel &    │ │                  │ │ (add via @tool)  │           │
│  │ per-user         │ │ Cold-start:      │ │                  │           │
│  │ overrides        │ │ hydrate Agent    │ │                  │           │
│  │                  │ │ from disk (40)   │ │                  │           │
│  │ Stateless        │ │                  │ │                  │           │
│  └──────────────────┘ └──────────────────┘ └──────────────────┘           │
│                                                                             │
│  STREAM ADAPTERS  (pi_stream/ — the provider seam)                         │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │  StreamFn protocol (pi-agent-core)                                   │  │
│  │  (model, context, options) → {events: AsyncIter, result: Awaitable}  │  │
│  │                                                                      │  │
│  │  ┌─────────────────────────────┐  ┌──────────────────────────────┐  │  │
│  │  │ Ocean adapter               │  │ Ollama adapter               │  │  │
│  │  │ pi_stream/ocean.py          │  │ pi_stream/ollama.py          │  │  │
│  │  │ Anthropic SSE format        │  │ OpenAI /v1/chat/completions  │  │  │
│  │  │ → Tuya Ocean Gateway        │  │ → Ollama (local)             │  │  │
│  │  └─────────────┬───────────────┘  └──────────────┬───────────────┘  │  │
│  └────────────────┼──────────────────────────────────┼──────────────────┘  │
│                   ▼                                  ▼                      │
│  ┌───────────────────────────┐    ┌────────────────────────────────┐       │
│  │  Tuya Ocean Gateway       │    │  Ollama (local)                │       │
│  │  → AWS Bedrock / Anthropic│    │  http://127.0.0.1:11434/v1     │       │
│  └───────────────────────────┘    └────────────────────────────────┘       │
│                                                                             │
│  CONFIGURATION                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │  config/agent.yaml   +   templates/*.md   +   env vars              │  │
│  │  • LLM provider/model (per-channel, per-user override)              │  │
│  │  • Reply policy (max_emojis, repair)                                │  │
│  │  • Prompt section toggles (per-channel, per-user)                   │  │
│  │  • WeCom credentials / Ocean scene-id                               │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Layer Responsibilities

| Layer | Files | Responsibility |
|-------|-------|----------------|
| **Loop** | `loop/turn.py`, `loop/runner.py` | Turn lifecycle — orchestrates all other layers |
| **Context** | `context/builder.py`, `context/post.py` | Assembles system prompt; post-processes output |
| **Memory** | `agent_sessions.py`, `memory/transcripts.py` | Agent cache (RAM, one per session) + disk persistence (JSONL) |
| **Tools** | `tools/registry.py`, `tools/builtin/` | Tool registration and error handling via `AgentTool` |
| **Stream adapters** | `pi_stream/ocean.py`, `pi_stream/ollama.py` | Provider-specific StreamFn implementations |

## Data Flow

```
User Input (stdin / WeCom WebSocket)
  ↓
run_turn()
  ├─ create_stream_fn()            → Ocean or Ollama StreamFn adapter
  ├─ build_system_prompt()         → identity + personality + skills + tools templates
  ├─ list_tools()                  → registered AgentTool list
  ├─ AgentSessionManager
  │    ├─ first turn: create Agent, hydrate from JsonlHistory
  │    └─ every turn: set_system_prompt(), set_tools()
  ├─ agent.prompt(user_text)       → pi-agent-core runs the agent loop:
  │    ├─ stream_fn() call         → provider API (SSE stream)
  │    ├─ ToolExecutionStartEvent  → transcript logging (tool_use)
  │    ├─ AgentTool.execute()      → Python tool function
  │    ├─ ToolExecutionEndEvent    → transcript logging (tool_result)
  │    └─ stream_fn() again        → LLM sees tool result (repeats until stop)
  ├─ cap_emojis()                  → enforce max_emojis reply policy
  ├─ optional repair pass          → direct stream_fn() call, no tool loop
  └─ JsonlHistory.append()         → persist turn to disk
  ↓
Output (stdout print / WeCom reply_stream)
```

## Key Design Choices

- **pi-agent-core for the agent loop** — stateful `Agent` per session replaces the hand-rolled `for _ in range(8)` tool loop; mirrors openclaw's TypeScript architecture
- **StreamFn as the provider seam** — `(model, context, options) → StreamResult`; adapters in `pi_stream/` translate provider SSE to pi-agent-core events
- **One Agent per session** — `AgentSessionManager` caches `Agent` instances keyed by `session_key`; conversation state lives inside the Agent, cold-started from `JsonlHistory`
- **System prompt applied every turn** — `agent.set_system_prompt()` called before each `agent.prompt()` so per-user overrides always take effect
- **Repair pass outside the agent loop** — emoji repair is a one-shot `stream_fn()` call with no tools, keeping pi-agent-core's loop clean
- **Tool exceptions surface as text** — `@tool` wrapper catches exceptions and returns them as `AgentToolResult` content so the LLM sees the error
- **Tool calls not replayed on cold-start** — model re-decides each session (simpler UX)
- **Stateless context** — templates re-read each turn; no caching
- **Per-user overrides** — WeCom users can each get a different personality, model, or LLM provider
