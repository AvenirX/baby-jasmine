from __future__ import annotations

import json
import os
from collections.abc import AsyncGenerator
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
from pi_agent_core import (
    AgentContext,
    AgentTool,
    AssistantMessage,
    Model,
    SimpleStreamOptions,
    StreamDoneEvent,
    StreamResult,
    StreamStartEvent,
    StreamTextDeltaEvent,
    StreamTextEndEvent,
    StreamTextStartEvent,
    StreamToolCallDeltaEvent,
    StreamToolCallEndEvent,
    StreamToolCallStartEvent,
    TextContent,
    ToolCall,
)
from pi_agent_core.types import AssistantMessageEvent

from baby_jasmine.config_models import ResolvedLlmConfig

DEFAULT_GATEWAY_URL = os.environ.get("OCEAN_GATEWAY_URL", "")
OCEAN_PROXY_PATH = "/ocean/v1.0/proxy/ai"

_STOP_MAP = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    "tool_use": "toolUse",
    "max_tokens": "length",
}


def _normalize_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return DEFAULT_GATEWAY_URL
    parts = urlsplit(raw)
    if parts.path in ("", "/"):
        return urlunsplit(
            (parts.scheme, parts.netloc, OCEAN_PROXY_PATH, parts.query, parts.fragment)
        )
    return raw.rstrip("/")


def _uses_v2_headers(url: str) -> bool:
    u = url or ""
    return "/ocean/v1" in u


def _gateway_headers(
    *, scene_id: str, provider: str, model_id: str, gateway_url: str
) -> dict[str, str]:
    h: dict[str, str] = {"Content-Type": "application/json"}
    if scene_id:
        h["scene-id"] = scene_id
    if _uses_v2_headers(gateway_url):
        h["version"] = "v2"
        h["stream"] = "true"
    h["provider"] = provider
    h["model-id"] = model_id
    return h


def _parse_sse_block(block: str) -> tuple[str | None, str | None]:
    ev: str | None = None
    data: str | None = None
    for line in block.splitlines():
        line = line.strip()
        if line.startswith("event:"):
            ev = line[6:].strip()
        elif line.startswith("data:"):
            data = line[5:].strip()
    return ev, data


def _serialize_messages(messages: list[Any]) -> list[dict[str, Any]]:
    """Convert pi-agent-core messages to Anthropic API wire format."""
    out: list[dict[str, Any]] = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        role = getattr(msg, "role", None)
        if role == "toolResult":
            # Batch consecutive tool results into one user message.
            batch: list[dict[str, Any]] = []
            while i < len(messages) and getattr(messages[i], "role", None) == "toolResult":
                tr = messages[i]
                text = "".join(c.text for c in tr.content if isinstance(c, TextContent))
                batch.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tr.tool_call_id,
                        "content": text,
                        "is_error": tr.is_error,
                    }
                )
                i += 1
            out.append({"role": "user", "content": batch})
        elif role == "user":
            blocks: list[dict[str, Any]] = []
            for c in msg.content:
                if isinstance(c, TextContent):
                    blocks.append({"type": "text", "text": c.text})
            out.append({"role": "user", "content": blocks})
            i += 1
        elif role == "assistant":
            blocks = []
            for c in msg.content:
                if isinstance(c, TextContent):
                    blocks.append({"type": "text", "text": c.text})
                elif isinstance(c, ToolCall):
                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": c.id,
                            "name": c.name,
                            "input": c.arguments,
                        }
                    )
            out.append({"role": "assistant", "content": blocks})
            i += 1
        else:
            i += 1
    return out


def _serialize_tool(t: AgentTool) -> dict[str, Any]:
    return {
        "name": t.name,
        "description": t.description,
        "input_schema": {
            "type": t.parameters.type,
            "properties": t.parameters.properties,
            "required": t.parameters.required,
        },
    }


async def _stream_events(
    *,
    gateway_url: str,
    scene_id: str,
    model_id: str,
    gateway_provider: str,
    system_prompt: str,
    messages: list[Any],
    tools: list[AgentTool],
    temperature: float | None,
    max_tokens: int,
    timeout_s: float,
    api: str,
    provider: str,
) -> AsyncGenerator[AssistantMessageEvent, None]:
    body: dict[str, Any] = {
        "messages": _serialize_messages(messages),
        "max_tokens": max_tokens,
    }
    if system_prompt:
        body["system"] = [
            {"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}
        ]
    if temperature is not None:
        body["temperature"] = temperature
    if tools:
        serialized_tools = [_serialize_tool(t) for t in tools]
        serialized_tools[-1]["cache_control"] = {"type": "ephemeral"}
        body["tools"] = serialized_tools

    headers = _gateway_headers(
        scene_id=scene_id,
        provider=gateway_provider,
        model_id=model_id,
        gateway_url=gateway_url,
    )

    content_blocks: dict[int, dict[str, Any]] = {}
    tool_json: dict[int, list[str]] = {}
    stop_reason = "stop"
    start_emitted = False

    def get_partial() -> AssistantMessage:
        content: list[Any] = []
        for idx in sorted(content_blocks.keys()):
            b = content_blocks[idx]
            if b["type"] == "text":
                content.append(TextContent(text=b.get("text", "")))
            elif b["type"] == "tool_use":
                raw_json = "".join(tool_json.get(idx, []))
                content.append(
                    ToolCall(
                        id=b["id"],
                        name=b["name"],
                        arguments=b.get("input", {}),
                        partial_json=raw_json or None,
                    )
                )
        return AssistantMessage(
            content=content, api=api, provider=provider, model=model_id, stop_reason=stop_reason
        )

    async with httpx.AsyncClient(timeout=timeout_s) as client:
        async with client.stream("POST", gateway_url, headers=headers, json=body) as resp:
            ct = resp.headers.get("content-type", "")
            if "amazon.eventstream" in ct:
                await resp.aread()
                raise RuntimeError(
                    "Ocean returned Bedrock binary event stream; "
                    "use a gateway that returns Anthropic SSE."
                )
            resp.raise_for_status()
            buf = ""
            async for chunk in resp.aiter_text():
                buf += chunk
                while "\n\n" in buf:
                    block, buf = buf.split("\n\n", 1)
                    if not block.strip():
                        continue
                    ev, data_raw = _parse_sse_block(block)
                    if not data_raw or data_raw == "[DONE]":
                        continue
                    try:
                        data = json.loads(data_raw)
                    except json.JSONDecodeError:
                        continue
                    t = data.get("type") or ev

                    if t == "content_block_start":
                        idx = int(data.get("index", 0))
                        cb = data.get("content_block") or {}
                        cb_type = cb.get("type")
                        if cb_type == "text":
                            content_blocks[idx] = {"type": "text", "text": cb.get("text") or ""}
                            if not start_emitted:
                                yield StreamStartEvent(partial=get_partial())
                                start_emitted = True
                            yield StreamTextStartEvent(content_index=idx, partial=get_partial())
                        elif cb_type == "tool_use":
                            content_blocks[idx] = {
                                "type": "tool_use",
                                "id": str(cb.get("id") or ""),
                                "name": str(cb.get("name") or ""),
                                "input": {},
                            }
                            tool_json[idx] = []
                            if not start_emitted:
                                yield StreamStartEvent(partial=get_partial())
                                start_emitted = True
                            yield StreamToolCallStartEvent(content_index=idx, partial=get_partial())

                    elif t == "content_block_delta":
                        idx = int(data.get("index", 0))
                        delta = data.get("delta") or {}
                        dtype = delta.get("type")
                        if dtype == "text_delta":
                            piece = str(delta.get("text") or "")
                            if piece and idx in content_blocks:
                                content_blocks[idx]["text"] = (
                                    content_blocks[idx].get("text", "") + piece
                                )
                                yield StreamTextDeltaEvent(
                                    content_index=idx, delta=piece, partial=get_partial()
                                )
                        elif dtype == "input_json_delta":
                            piece = str(delta.get("partial_json") or "")
                            tool_json.setdefault(idx, []).append(piece)
                            yield StreamToolCallDeltaEvent(
                                content_index=idx, delta=piece, partial=get_partial()
                            )

                    elif t == "content_block_stop":
                        idx = int(data.get("index", 0))
                        if idx in tool_json:
                            raw = "".join(tool_json[idx])
                            try:
                                parsed: Any = json.loads(raw) if raw.strip() else {}
                            except json.JSONDecodeError:
                                parsed = {"_raw": raw}
                            if isinstance(parsed, dict):
                                content_blocks[idx]["input"] = parsed
                            b = content_blocks[idx]
                            tc = ToolCall(id=b["id"], name=b["name"], arguments=b.get("input", {}))
                            yield StreamToolCallEndEvent(
                                content_index=idx, tool_call=tc, partial=get_partial()
                            )
                        elif idx in content_blocks:
                            yield StreamTextEndEvent(
                                content_index=idx,
                                content=content_blocks[idx].get("text", ""),
                                partial=get_partial(),
                            )

                    elif t == "message_delta":
                        delta = data.get("delta") or {}
                        sr = delta.get("stop_reason")
                        if isinstance(sr, str):
                            stop_reason = _STOP_MAP.get(sr, "stop")
                        usage = data.get("usage") or {}
                        cache_read = usage.get("cache_read_input_tokens", 0)
                        cache_write = usage.get("cache_creation_input_tokens", 0)
                        if cache_read or cache_write:
                            print(
                                f"[cache] read={cache_read} write={cache_write}",
                                flush=True,
                            )

    if not start_emitted:
        yield StreamStartEvent(partial=get_partial())

    final = get_partial()
    yield StreamDoneEvent(reason=final.stop_reason, message=final)


def make_ocean_stream_fn(resolved: ResolvedLlmConfig):
    """Return a StreamFn that calls the Tuya Ocean gateway."""
    gateway_url = _normalize_url(resolved.ocean_gateway_url or "")
    scene_id = resolved.ocean_scene_id or ""
    model_id = resolved.model
    temperature = resolved.temperature

    async def stream_fn(
        model: Model, context: AgentContext, options: SimpleStreamOptions
    ) -> StreamResult:
        holder: list[AssistantMessage] = []

        async def gen() -> AsyncGenerator[AssistantMessageEvent, None]:
            async for event in _stream_events(
                gateway_url=gateway_url,
                scene_id=scene_id,
                model_id=model_id,
                gateway_provider="BEDROCK",
                system_prompt=context.system_prompt,
                messages=context.messages,
                tools=context.tools,
                temperature=temperature if temperature is not None else options.temperature,
                max_tokens=options.max_tokens or 4096,
                timeout_s=300.0,
                api=model.api,
                provider=model.provider,
            ):
                if isinstance(event, StreamDoneEvent):
                    holder.append(event.message)
                yield event

        async def result() -> AssistantMessage:
            return holder[0] if holder else AssistantMessage()

        return {"events": gen(), "result": result}

    return stream_fn
