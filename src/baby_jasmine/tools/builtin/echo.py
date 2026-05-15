from __future__ import annotations

from typing import Any

from baby_jasmine.tools.registry import tool


@tool(
    name="echo",
    description="Echo back the provided text. Useful for verifying tool calls.",
    input_schema={
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
        "additionalProperties": False,
    },
)
def echo(args: dict[str, Any]) -> str:
    return str(args.get("text") or "")
