from __future__ import annotations

import json

from pi_agent_core import (
    AgentTool,
    AgentToolSchema,
    AssistantMessage,
    TextContent,
    ToolCall,
    ToolResultMessage,
    UserMessage,
)

from baby_jasmine.pi_stream.ollama import _serialize_messages, _serialize_tools


def test_serialize_plain_user():
    msg = UserMessage(content=[TextContent(text="hi")])
    out = _serialize_messages([msg], system_prompt="sys")
    assert out == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
    ]


def test_serialize_assistant_with_tool_call():
    msg = AssistantMessage(
        content=[
            TextContent(text="calling"),
            ToolCall(id="u1", name="echo", arguments={"text": "hi"}),
        ]
    )
    out = _serialize_messages([msg], system_prompt="")
    assert len(out) == 1
    entry = out[0]
    assert entry["role"] == "assistant"
    assert entry["content"] == "calling"
    assert len(entry["tool_calls"]) == 1
    tc = entry["tool_calls"][0]
    assert tc["id"] == "u1"
    assert tc["type"] == "function"
    assert tc["function"]["name"] == "echo"
    assert json.loads(tc["function"]["arguments"]) == {"text": "hi"}


def test_serialize_tool_result_becomes_role_tool():
    msg = ToolResultMessage(tool_call_id="u1", tool_name="echo", content=[TextContent(text="ok")])
    out = _serialize_messages([msg], system_prompt="")
    assert out == [{"role": "tool", "tool_call_id": "u1", "content": "ok"}]


def test_serialize_tools_wraps_in_function_type():
    async def _noop_execute(tc_id, params, cancel=None, on_update=None):
        from pi_agent_core import AgentToolResult

        return AgentToolResult()

    t = AgentTool(
        name="echo",
        description="d",
        parameters=AgentToolSchema(properties={}),
        execute=_noop_execute,
    )
    result = _serialize_tools([t])
    assert result == [
        {
            "type": "function",
            "function": {
                "name": "echo",
                "description": "d",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        }
    ]
