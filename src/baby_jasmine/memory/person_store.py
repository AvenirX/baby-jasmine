from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from baby_jasmine.memory.context import get_memory_root

FactCategory = Literal["preference", "fact", "note"]
FactSource = Literal["private", "group", "inferred"]


@dataclass
class Fact:
    id: str
    category: FactCategory
    content: str
    source: FactSource
    ts: str
    confidence: str = "medium"
    group_id: str | None = None


@dataclass
class PersonMemory:
    wecom_userid: str
    display_name: str | None = None
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    facts: list[Fact] = field(default_factory=list)


def _person_path(userid: str) -> Path:
    return get_memory_root() / "persons" / f"{userid}.json"


def load_person(userid: str) -> PersonMemory:
    path = _person_path(userid)
    if not path.is_file():
        return PersonMemory(wecom_userid=userid)
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    facts = [
        Fact(
            id=f["id"],
            category=f["category"],
            content=f["content"],
            source=f["source"],
            ts=f["ts"],
            confidence=f.get("confidence", "medium"),
            group_id=f.get("group_id"),
        )
        for f in data.get("facts", [])
    ]
    return PersonMemory(
        wecom_userid=userid,
        display_name=data.get("display_name"),
        updated_at=data.get("updated_at", datetime.now(UTC).isoformat()),
        facts=facts,
    )


def save_person(person: PersonMemory) -> None:
    path = _person_path(person.wecom_userid)
    person.updated_at = datetime.now(UTC).isoformat()
    data = {
        "wecom_userid": person.wecom_userid,
        "display_name": person.display_name,
        "updated_at": person.updated_at,
        "facts": [
            {
                "id": f.id,
                "category": f.category,
                "content": f.content,
                "source": f.source,
                "ts": f.ts,
                "confidence": f.confidence,
                **({"group_id": f.group_id} if f.group_id else {}),
            }
            for f in person.facts
        ],
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def add_fact(
    userid: str,
    *,
    category: FactCategory,
    content: str,
    source: FactSource,
    confidence: str = "medium",
    group_id: str | None = None,
) -> Fact:
    person = load_person(userid)
    fact = Fact(
        id=f"f{uuid.uuid4().hex[:8]}",
        category=category,
        content=content,
        source=source,
        ts=datetime.now(UTC).isoformat(),
        confidence=confidence,
        group_id=group_id,
    )
    person.facts.append(fact)
    save_person(person)
    return fact
