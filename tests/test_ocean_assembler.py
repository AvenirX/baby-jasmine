from __future__ import annotations

from pi_agent_core import AssistantMessage, TextContent, ToolCall, ToolResultMessage, UserMessage

from baby_jasmine.pi_stream.ocean import (
    _normalize_url,
    _serialize_messages,
)


def test_normalize_url_appends_path_for_origin_only():
    assert _normalize_url("https://ocean.example.com:7799") == (
        "https://ocean.example.com:7799/ocean/v1.0/proxy/ai"
    )


def test_normalize_url_leaves_full_url_unchanged():
    full = "https://ocean.example.com:7799/ocean/v1.0/proxy/ai"
    assert _normalize_url(full) == full


def test_serialize_user_message():
    msg = UserMessage(content=[TextContent(text="hello")])
    out = _serialize_messages([msg])
    assert out == [{"role": "user", "content": [{"type": "text", "text": "hello"}]}]


def test_serialize_assistant_with_tool_call():
    msg = AssistantMessage(
        content=[
            TextContent(text="thinking"),
            ToolCall(id="u1", name="echo", arguments={"text": "hi"}),
        ]
    )
    out = _serialize_messages([msg])
    assert len(out) == 1
    assert out[0]["role"] == "assistant"
    content = out[0]["content"]
    assert {"type": "text", "text": "thinking"} in content
    assert {"type": "tool_use", "id": "u1", "name": "echo", "input": {"text": "hi"}} in content


def test_serialize_tool_results_batched():
    tr1 = ToolResultMessage(tool_call_id="u1", tool_name="a", content=[TextContent(text="res1")])
    tr2 = ToolResultMessage(tool_call_id="u2", tool_name="b", content=[TextContent(text="res2")])
    out = _serialize_messages([tr1, tr2])
    assert len(out) == 1
    assert out[0]["role"] == "user"
    batch = out[0]["content"]
    assert len(batch) == 2
    assert batch[0] == {
        "type": "tool_result",
        "tool_use_id": "u1",
        "content": "res1",
        "is_error": False,
    }
    assert batch[1] == {
        "type": "tool_result",
        "tool_use_id": "u2",
        "content": "res2",
        "is_error": False,
    }
