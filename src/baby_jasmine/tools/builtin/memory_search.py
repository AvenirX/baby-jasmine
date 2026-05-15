from __future__ import annotations

from typing import Any

from baby_jasmine.memory.context import get_transcripts_root
from baby_jasmine.memory.transcripts import search_transcripts
from baby_jasmine.tools.registry import tool


@tool(
    name="search_history",
    description=(
        "Search through conversation history transcripts. "
        "Returns matching messages with timestamps, roles, and source (private/group). "
        "Use to recall past conversations or find when something was mentioned."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Text to search for (case-insensitive substring match)",
            },
            "wecom_userid": {
                "type": "string",
                "description": "Filter to messages from this WeCom user ID",
            },
            "session_key": {
                "type": "string",
                "description": "Filter to an exact session"
                " (e.g. 'wecom:private:user123' or 'wecom:group:wrZLrWCQ...')",
            },
            "date_from": {
                "type": "string",
                "description": "Start date filter YYYY-MM-DD (inclusive)",
            },
            "date_to": {
                "type": "string",
                "description": "End date filter YYYY-MM-DD (inclusive)",
            },
            "limit": {
                "type": "integer",
                "description": "Max results to return (default 20, max 50)",
                "default": 20,
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    },
)
def search_history(args: dict[str, Any]) -> str:
    query = args["query"]
    limit = min(int(args.get("limit") or 20), 50)
    results = search_transcripts(
        get_transcripts_root(),
        query,
        wecom_userid=args.get("wecom_userid") or None,
        session_key=args.get("session_key") or None,
        date_from=args.get("date_from") or None,
        date_to=args.get("date_to") or None,
        limit=limit,
    )
    if not results:
        return f'No results found for "{query}".'

    lines = [f'Search results for "{query}" ({len(results)} found):\n']
    for r in results:
        ts = r.get("ts", "")[:16].replace("T", " ")
        source = r.get("source", r.get("session_key", ""))
        role = r.get("role", "")
        text = r.get("text", "")
        if len(text) > 200:
            text = text[:200] + "…"
        lines.append(f"[{ts}] [{source}] {role}: {text}")
    return "\n".join(lines)
