from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from baby_jasmine.tools.registry import tool


@tool(
    name="time_now",
    description="Return the current UTC time as ISO 8601. Takes no arguments.",
    input_schema={"type": "object", "properties": {}, "additionalProperties": False},
)
def time_now(_args: dict[str, Any]) -> str:
    return datetime.now(UTC).isoformat()
