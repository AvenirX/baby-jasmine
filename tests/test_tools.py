from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from pi_agent_core import (
    AssistantMessage,
    StreamDoneEvent,
    TextContent,
    ToolCall,
)

from baby_jasmine.agent_sessions import AgentSessionManager
from baby_jasmine.config_models import AgentConfig, ReplyPolicy
from baby_jasmine.loop.turn import run_turn
from baby_jasmine.memory.transcripts import JsonlHistory, transcript_path
from baby_jasmine.tools.registry import clear, list_tools, register, tool


@pytest.fixture(autouse=True)
def _isolate_registry():
    clear()
    yield
    clear()


def _make_stream_fn(responses: list[AssistantMessage]):
    call_index = [0]

    def stream_fn(model, context, options):
        msg = responses[call_index[0]]
        call_index[0] += 1

        async def gen():
            yield StreamDoneEvent(reason=msg.stop_reason, message=msg)

        async def result():
            return msg

        return {"events": gen(), "result": result}

    stream_fn._calls = call_index
    return stream_fn


def test_register_and_list_tools() -> None:
    register(
        name="noop",
        description="do nothing",
        input_schema={"type": "object", "properties": {}},
        fn=lambda _a: "ok",
    )
    tools = list_tools()
    assert len(tools) == 1
    assert tools[0].name == "noop"


def test_tool_decorator_execute() -> None:
    @tool(
        name="add",
        description="add a and b",
        input_schema={
            "type": "object",
            "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
            "required": ["a", "b"],
        },
    )
    def add(args: dict) -> str:
        return str(args["a"] + args["b"])

    t = list_tools()[0]
    result = asyncio.run(t.execute("call1", {"a": 2, "b": 3}))
    assert result.content[0].text == "5"


def test_tool_exception_returns_error_text() -> None:
    @tool(
        name="boom",
        description="raises",
        input_schema={"type": "object", "properties": {}},
    )
    def boom(_a: dict) -> str:
        raise ValueError("bad")

    t = list_tools()[0]
    result = asyncio.run(t.execute("b1", {}))
    assert "ValueError" in result.content[0].text
    assert "bad" in result.content[0].text


def test_builtin_tools_register() -> None:
    import importlib

    clear()
    from baby_jasmine.tools.builtin import echo as echo_mod
    from baby_jasmine.tools.builtin import time_now as time_now_mod

    importlib.reload(echo_mod)
    importlib.reload(time_now_mod)

    tools_by_name = {t.name: t for t in list_tools()}
    assert {"time_now", "echo"}.issubset(tools_by_name)

    echo_result = asyncio.run(tools_by_name["echo"].execute("e1", {"text": "hi"}))
    assert echo_result.content[0].text == "hi"


def test_run_turn_executes_tool_and_returns_final(tmp_path: Path) -> None:
    register(
        name="greet",
        description="say hi to name",
        input_schema={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
        fn=lambda a: f"hi {a['name']}",
    )

    cfg = AgentConfig()
    cfg.reply = ReplyPolicy(max_emojis=10, repair_enabled=False)
    project_root = tmp_path
    (project_root / "templates").mkdir()
    (project_root / "templates" / "identity.md").write_text("id", encoding="utf-8")
    hist = JsonlHistory(root=tmp_path / "t")
    sessions = AgentSessionManager()

    fake_fn = _make_stream_fn(
        [
            AssistantMessage(
                content=[ToolCall(id="u1", name="greet", arguments={"name": "Alain"})],
                stop_reason="toolUse",
            ),
            AssistantMessage(
                content=[TextContent(text="Said: hi Alain")],
                stop_reason="stop",
            ),
        ]
    )

    async def _run() -> str:
        with patch("baby_jasmine.loop.turn.create_stream_fn", return_value=fake_fn):
            return await run_turn(
                cfg=cfg,
                project_root=project_root,
                history_store=hist,
                sessions=sessions,
                session_key="s1",
                channel="local",
                wecom_userid=None,
                user_text="please greet me",
            )

    out = asyncio.run(_run())
    assert out == "Said: hi Alain"
    assert fake_fn._calls[0] == 2


def test_run_turn_logs_tool_use_and_tool_result(tmp_path: Path) -> None:
    register(
        name="pong",
        description="returns pong",
        input_schema={"type": "object", "properties": {}},
        fn=lambda _a: "pong",
    )
    cfg = AgentConfig()
    cfg.reply = ReplyPolicy(max_emojis=10, repair_enabled=False)
    project_root = tmp_path
    (project_root / "templates").mkdir()
    (project_root / "templates" / "identity.md").write_text("id", encoding="utf-8")
    hist = JsonlHistory(root=tmp_path / "t")
    sessions = AgentSessionManager()

    fake_fn = _make_stream_fn(
        [
            AssistantMessage(
                content=[ToolCall(id="u2", name="pong", arguments={})],
                stop_reason="toolUse",
            ),
            AssistantMessage(
                content=[TextContent(text="done")],
                stop_reason="stop",
            ),
        ]
    )

    async def _run() -> str:
        with patch("baby_jasmine.loop.turn.create_stream_fn", return_value=fake_fn):
            return await run_turn(
                cfg=cfg,
                project_root=project_root,
                history_store=hist,
                sessions=sessions,
                session_key="s2",
                channel="local",
                wecom_userid=None,
                user_text="ping",
            )

    asyncio.run(_run())
    p = transcript_path(tmp_path / "t")
    lines = p.read_text(encoding="utf-8").splitlines()
    roles = [json.loads(x)["role"] for x in lines]
    assert roles == ["user", "tool_use", "tool_result", "assistant"]
    tool_use_payload = json.loads(json.loads(lines[1])["text"])
    assert tool_use_payload == {"id": "u2", "name": "pong", "input": {}}
    tool_result_rec = json.loads(lines[2])
    assert tool_result_rec["text"] == "pong"
    assert tool_result_rec["meta"]["tool_use_id"] == "u2"
    assert tool_result_rec["meta"]["is_error"] is False
