from __future__ import annotations

from typing import Any

from baby_jasmine.memory.context import get_self_context_path
from baby_jasmine.tools.registry import tool


@tool(
    name="update_self_context",
    description=(
        "Overwrite your persistent self-context file with new markdown content. "
        "Use this to remember things about yourself, your experiences, and relationships "
        "across conversations. Write in first person. The full file is replaced each call."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "Full markdown content for your self-context. Replaces existing content.",  # noqa: E501
            }
        },
        "required": ["content"],
        "additionalProperties": False,
    },
)
def update_self_context(args: dict[str, Any]) -> str:
    content = args["content"]
    path = get_self_context_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return f"Self-context updated ({len(content)} chars)."
