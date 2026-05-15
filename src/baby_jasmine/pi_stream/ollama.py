from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

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

DEFAULT_OLLAMA_BASE = "http://127.0.0.1:11434/v1"

_FINISH_MAP = {
    "stop": "stop",
    "length": "length",
    "tool_calls": "toolUse",
    "function_call": "toolUse",
}


def _normalize_base(base: str) -> str:
    b = (base or "").rstrip("/")
    return b if b.endswith("/v1") else f"{b}/v1"


def _serialize_messages(messages: list[Any], system_prompt: str) -> list[dict[str, Any]]:
    """Convert pi-agent-core messages to OpenAI chat.completions format."""
    out: list[dict[str, Any]] = []
    if system_prompt:
        out.append({"role": "system", "content": system_prompt})
    for msg in messages:
        role = getattr(msg, "role", None)
        if role == "user":
            texts = [c.text for c in msg.content if isinstance(c, TextContent)]
            out.append({"role": "user", "content": "".join(texts)})
        elif role == "assistant":
            text_parts = [c.text for c in msg.content if isinstance(c, TextContent)]
            tool_calls = [
                {
                    "id": c.id,
                    "type": "function",
                    "function": {
                        "name": c.name,
                        "arguments": json.dumps(c.arguments, ensure_ascii=False),
                    },
                }
                for c in msg.content
                if isinstance(c, ToolCall)
            ]
            entry: dict[str, Any] = {"role": "assistant", "content": "".join(text_parts) or None}
            if tool_calls:
                entry["tool_calls"] = tool_calls
            out.append(entry)
        elif role == "toolResult":
            text = "".join(c.text for c in msg.content if isinstance(c, TextContent))
            out.append({"role": "tool", "tool_call_id": msg.tool_call_id, "content": text})
    return out


def _serialize_tools(tools: list[AgentTool]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": {
                    "type": t.parameters.type,
                    "properties": t.parameters.properties,
                    "required": t.parameters.required,
                },
            },
        }
        for t in tools
    ]


async def _stream_events(
    *,
    base_url: str,
    model_id: str,
    system_prompt: str,
    messages: list[Any],
    tools: list[AgentTool],
    temperature: float | None,
    timeout_s: float,
    api: str,
    provider: str,
) -> AsyncGenerator[AssistantMessageEvent, None]:
    url = f"{base_url}/chat/completions"
    payload: dict[str, Any] = {
        "model": model_id,
        "messages": _serialize_messages(messages, system_prompt),
        "stream": True,
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if tools:
        payload["tools"] = _serialize_tools(tools)

    text_parts: list[str] = []
    # tool_call accumulator: {idx: {id, name, arguments: [str]}}
    tool_acc: dict[int, dict[str, Any]] = {}
    stop_reason = "stop"
    start_emitted = False

    def get_partial() -> AssistantMessage:
        content: list[Any] = []
        if text_parts:
            content.append(TextContent(text="".join(text_parts)))
        for idx in sorted(tool_acc.keys()):
            e = tool_acc[idx]
            content.append(
                ToolCall(
                    id=e.get("id", ""),
                    name=e.get("name", ""),
                    arguments={},
                    partial_json="".join(e.get("arguments", [])) or None,
                )
            )
        return AssistantMessage(
            content=content, api=api, provider=provider, model=model_id, stop_reason=stop_reason
        )

    async with httpx.AsyncClient(timeout=timeout_s) as client:
        async with client.stream("POST", url, json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line or line.startswith(":"):
                    continue
                if not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if raw == "[DONE]":
                    break
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                choices = data.get("choices") or []
                if not choices:
                    continue
                ch0 = choices[0] or {}
                delta = ch0.get("delta") or {}
                piece = delta.get("content")
                if piece:
                    piece = str(piece)
                    text_parts.append(piece)
                    if not start_emitted:
                        yield StreamStartEvent(partial=get_partial())
                        yield StreamTextStartEvent(content_index=0, partial=get_partial())
                        start_emitted = True
                    yield StreamTextDeltaEvent(content_index=0, delta=piece, partial=get_partial())

                tc_deltas = delta.get("tool_calls") or []
                for tcd in tc_deltas:
                    idx = int(tcd.get("index", 0))
                    entry = tool_acc.setdefault(idx, {"id": "", "name": "", "arguments": []})
                    if tcd.get("id"):
                        entry["id"] = str(tcd["id"])
                    fn = tcd.get("function") or {}
                    if fn.get("name"):
                        entry["name"] = str(fn["name"])
                    if fn.get("arguments") is not None:
                        entry["arguments"].append(str(fn["arguments"]))
                    if not start_emitted:
                        yield StreamStartEvent(partial=get_partial())
                        start_emitted = True
                    yield StreamToolCallStartEvent(content_index=idx, partial=get_partial())
                    if fn.get("arguments"):
                        yield StreamToolCallDeltaEvent(
                            content_index=idx, delta=str(fn["arguments"]), partial=get_partial()
                        )

                finish = ch0.get("finish_reason")
                if isinstance(finish, str) and finish in _FINISH_MAP:
                    stop_reason = _FINISH_MAP[finish]

    # Emit text end event if we had text
    if text_parts:
        full_text = "".join(text_parts)
        yield StreamTextEndEvent(content_index=0, content=full_text, partial=get_partial())

    # Emit tool call end events for each accumulated tool call
    for idx, entry in sorted(tool_acc.items()):
        raw_args = "".join(entry.get("arguments", []))
        try:
            parsed = json.loads(raw_args) if raw_args.strip() else {}
        except json.JSONDecodeError:
            parsed = {"_raw": raw_args}
        tc = ToolCall(
            id=entry.get("id", f"call_{idx}"),
            name=entry.get("name", ""),
            arguments=parsed,
        )
        yield StreamToolCallEndEvent(content_index=idx, tool_call=tc, partial=get_partial())

    if not start_emitted:
        yield StreamStartEvent(partial=get_partial())

    final = get_partial()
    yield StreamDoneEvent(reason=final.stop_reason, message=final)


def make_ollama_stream_fn(resolved: ResolvedLlmConfig):
    """Return a StreamFn that calls an Ollama-compatible endpoint."""
    base_url = _normalize_base(resolved.ollama_base_url or DEFAULT_OLLAMA_BASE)
    model_id = resolved.model
    temperature = resolved.temperature

    async def stream_fn(
        model: Model, context: AgentContext, options: SimpleStreamOptions
    ) -> StreamResult:
        holder: list[AssistantMessage] = []

        async def gen() -> AsyncGenerator[AssistantMessageEvent, None]:
            async for event in _stream_events(
                base_url=base_url,
                model_id=model_id,
                system_prompt=context.system_prompt,
                messages=context.messages,
                tools=context.tools,
                temperature=temperature if temperature is not None else options.temperature,
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
