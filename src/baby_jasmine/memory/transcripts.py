from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from pi_agent_core import AssistantMessage, TextContent, UserMessage
from pi_agent_core.types import Message


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def transcript_path(root: Path, day: datetime | None = None) -> Path:
    d = day or datetime.now(UTC)
    ym = d.strftime("%Y-%m")
    ymd = d.strftime("%Y-%m-%d")
    return root / ym / f"{ymd}.jsonl"


@dataclass
class JsonlHistory:
    root: Path

    def append(
        self,
        *,
        session_key: str,
        channel: str,
        role: str,
        text: str,
        wecom_userid: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        path = transcript_path(self.root)
        path.parent.mkdir(parents=True, exist_ok=True)
        rec = {
            "ts": _utc_now_iso(),
            "session_key": session_key,
            "channel": channel,
            "role": role,
            "text": text,
        }
        if wecom_userid:
            rec["wecom_userid"] = wecom_userid
        if meta:
            rec["meta"] = meta
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()

    def load_recent_messages(
        self,
        session_key: str,
        *,
        limit: int = 40,
        day: datetime | None = None,
    ) -> list[Message]:
        """Reconstruct text-only turns from transcripts.

        Tool_use / tool_result rows are skipped: they're logged for auditability but
        don't need to replay on restart — the model re-decides whether to call tools.
        """
        path = transcript_path(self.root, day)
        if not path.is_file():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        out: list[Message] = []
        for line in lines:
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("session_key") != session_key:
                continue
            role = rec.get("role")
            text = rec.get("text") or rec.get("content") or ""
            if not text:
                continue
            if role == "user":
                out.append(UserMessage(content=[TextContent(text=text)]))
            elif role == "assistant":
                out.append(AssistantMessage(content=[TextContent(text=text)]))
        return out[-limit:]


def _file_date(path: Path) -> date | None:
    try:
        return date.fromisoformat(path.stem)
    except ValueError:
        return None


def search_transcripts(
    root: Path,
    query: str,
    *,
    wecom_userid: str | None = None,
    session_key: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Grep JSONL transcript files and return matching records.

    Files are scanned newest-first. Each record is returned with an added
    ``source`` field derived from the session_key prefix (e.g. "private:user123").
    """
    d_from = date.fromisoformat(date_from) if date_from else None
    d_to = date.fromisoformat(date_to) if date_to else None
    pattern = re.compile(re.escape(query), re.IGNORECASE)

    # Collect all JSONL files sorted newest-first
    jsonl_files = sorted(root.glob("*/*.jsonl"), key=lambda p: p.stem, reverse=True)

    results: list[dict[str, Any]] = []
    for jfile in jsonl_files:
        fdate = _file_date(jfile)
        if fdate is not None:
            if d_from and fdate < d_from:
                continue
            if d_to and fdate > d_to:
                continue
        lines = jfile.read_text(encoding="utf-8").splitlines()
        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if session_key and rec.get("session_key") != session_key:
                continue
            if wecom_userid and rec.get("wecom_userid") != wecom_userid:
                continue
            text = rec.get("text", "")
            if not pattern.search(text):
                continue
            sk = rec.get("session_key", "")
            if sk.startswith("wecom:private:"):
                source = f"private:{sk[len('wecom:private:') :]}"
            elif sk.startswith("wecom:group:"):
                source = f"group:{sk[len('wecom:group:') :]}"
            else:
                source = sk
            results.append({**rec, "source": source})
            if len(results) >= limit:
                return results
    return results
