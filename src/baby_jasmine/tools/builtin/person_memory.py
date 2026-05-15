from __future__ import annotations

from typing import Any

from baby_jasmine.memory.context import get_transcripts_root
from baby_jasmine.memory.person_store import FactCategory, FactSource, add_fact, load_person
from baby_jasmine.memory.transcripts import search_transcripts
from baby_jasmine.tools.registry import tool


@tool(
    name="recall_person",
    description=(
        "Recall saved facts and preferences about a WeCom user. "
        "In group context, private-source facts are returned tagged [PRIVATE] — "
        "use them to inform your response but do not reveal them openly."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "wecom_userid": {
                "type": "string",
                "description": "WeCom user ID to recall",
            },
            "current_context": {
                "type": "string",
                "enum": ["private", "group"],
                "description": "Current chat context — affects privacy tagging",
            },
        },
        "required": ["wecom_userid", "current_context"],
        "additionalProperties": False,
    },
)
def recall_person(args: dict[str, Any]) -> str:
    userid = args["wecom_userid"]
    context = args.get("current_context", "private")
    person = load_person(userid)

    name_line = f"display_name: {person.display_name}" if person.display_name else ""
    header = f"## Memory: {userid}" + (f" ({person.display_name})" if person.display_name else "")

    if not person.facts:
        return f"{header}\nNo saved facts yet."

    lines = [header]
    if name_line:
        lines.append(name_line)
    lines.append("")

    for f in person.facts:
        ts = f.ts[:10]
        tag = ""
        if context == "group" and f.source == "private":
            tag = " ← [PRIVATE - do not disclose in group]"
        label = f"[{f.category}]"
        conf = f" (confidence: {f.confidence})" if f.confidence != "medium" else ""
        group = f" (group: {f.group_id})" if f.group_id else ""
        lines.append(f"- {label} {f.content} (from {f.source} chat, {ts}){conf}{group}{tag}")

    return "\n".join(lines)


@tool(
    name="save_memory",
    description=(
        "Save an important fact or preference about a WeCom user for future recall. "
        "Call this proactively when you learn something noteworthy about a person."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "wecom_userid": {
                "type": "string",
                "description": "WeCom user ID this fact is about",
            },
            "category": {
                "type": "string",
                "enum": ["preference", "fact", "note"],
                "description": "Type of information",
            },
            "content": {
                "type": "string",
                "description": "The fact or preference to remember",
            },
            "source": {
                "type": "string",
                "enum": ["private", "group", "inferred"],
                "description": "Where this was learned —"
                " use 'private' for private chats, 'group' for group chats",
            },
            "confidence": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": "How confident you are (default: medium)",
            },
            "group_id": {
                "type": "string",
                "description": "WeCom group chat ID — required when source is 'group'",
            },
        },
        "required": ["wecom_userid", "category", "content", "source"],
        "additionalProperties": False,
    },
)
def save_memory(args: dict[str, Any]) -> str:
    userid = args["wecom_userid"]
    category: FactCategory = args["category"]
    content = args["content"]
    source: FactSource = args["source"]
    confidence = args.get("confidence") or "medium"
    group_id = args.get("group_id") or None
    fact = add_fact(
        userid,
        category=category,
        content=content,
        source=source,
        confidence=confidence,
        group_id=group_id,
    )
    return f"Saved [{fact.category}] fact for {userid} (id: {fact.id}): {fact.content}"


@tool(
    name="list_person_summary",
    description=(
        "Return a structured summary of everything known about a WeCom user: "
        "saved facts plus recent transcript excerpts from both private and group sessions. "
        "Use as input for writing a person summary."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "wecom_userid": {
                "type": "string",
                "description": "WeCom user ID to summarize",
            },
            "scope": {
                "type": "string",
                "enum": ["all", "preferences", "facts"],
                "description": "Which facts to include (default: all)",
            },
        },
        "required": ["wecom_userid"],
        "additionalProperties": False,
    },
)
def list_person_summary(args: dict[str, Any]) -> str:
    userid = args["wecom_userid"]
    scope = args.get("scope") or "all"
    person = load_person(userid)

    lines = [
        f"## Full Summary: {userid}" + (f" ({person.display_name})" if person.display_name else "")
    ]

    # Saved facts section
    facts = person.facts
    if scope == "preferences":
        facts = [f for f in facts if f.category == "preference"]
    elif scope == "facts":
        facts = [f for f in facts if f.category == "fact"]

    if facts:
        lines.append("\n**Saved facts:**")
        for f in facts:
            lines.append(f"- [{f.category}] {f.content} (source: {f.source}, {f.ts[:10]})")
    else:
        lines.append("\n**Saved facts:** none")

    # Recent transcript excerpts from both sessions
    root = get_transcripts_root()
    for session_label, sk in [
        ("private", f"wecom:private:{userid}"),
        ("group", None),
    ]:
        if sk is not None:
            excerpts = search_transcripts(
                root,
                "",
                session_key=sk,
                limit=5,
            )
        else:
            excerpts = search_transcripts(
                root,
                "",
                wecom_userid=userid,
                limit=10,
            )
            excerpts = [e for e in excerpts if e.get("session_key", "").startswith("wecom:group:")][
                :5
            ]

        if excerpts:
            lines.append(f"\n**Recent {session_label} messages:**")
            for r in excerpts:
                ts = r.get("ts", "")[:16].replace("T", " ")
                role = r.get("role", "")
                text = r.get("text", "")
                if len(text) > 150:
                    text = text[:150] + "…"
                lines.append(f"[{ts}] {role}: {text}")

    return "\n".join(lines)
