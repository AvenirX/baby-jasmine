from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from pi_agent_core import AgentTool, AgentToolResult, AgentToolSchema, TextContent

ToolFn = Callable[[dict[str, Any]], Awaitable[str] | str]

_REGISTRY: dict[str, AgentTool] = {}
_FNS: dict[str, ToolFn] = {}


def register(
    *,
    name: str,
    description: str,
    input_schema: dict[str, Any],
    fn: ToolFn,
) -> None:
    schema = AgentToolSchema(
        properties=input_schema.get("properties", {}),
        required=input_schema.get("required", []),
    )

    async def _execute(
        tool_call_id: str,
        params: dict[str, Any],
        cancel_event: Any = None,
        on_update: Any = None,
    ) -> AgentToolResult:
        try:
            result = fn(params)
            if inspect.isawaitable(result):
                result = await result
            return AgentToolResult(content=[TextContent(text=str(result))])
        except Exception as exc:
            return AgentToolResult(content=[TextContent(text=f"{type(exc).__name__}: {exc}")])

    _REGISTRY[name] = AgentTool(
        name=name, description=description, parameters=schema, execute=_execute
    )
    _FNS[name] = fn


def tool(
    *,
    name: str,
    description: str,
    input_schema: dict[str, Any],
) -> Callable[[ToolFn], ToolFn]:
    def _decorate(fn: ToolFn) -> ToolFn:
        register(name=name, description=description, input_schema=input_schema, fn=fn)
        return fn

    return _decorate


def list_tools() -> list[AgentTool]:
    return list(_REGISTRY.values())


def clear() -> None:
    _REGISTRY.clear()
    _FNS.clear()
