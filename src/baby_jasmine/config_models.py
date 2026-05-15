from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Provider = Literal["ocean", "ollama"]
Channel = Literal["local", "wecom"]


@dataclass
class ResolvedLlmConfig:
    provider: Provider
    model: str
    ocean_gateway_url: str | None = None
    ocean_scene_id: str | None = None
    ollama_base_url: str | None = None
    temperature: float | None = None


@dataclass
class SectionChannels:
    local_enabled: bool = True
    wecom_enabled: bool = True
    wecom_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class SectionSpec:
    template: str
    channels: SectionChannels = field(default_factory=SectionChannels)


@dataclass
class LlmChannels:
    local: dict[str, Any] = field(default_factory=dict)
    wecom: dict[str, Any] = field(default_factory=dict)
    wecom_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class ReplyPolicy:
    max_emojis: int = 4
    repair_enabled: bool = False
    emoji_only: bool = False
    wecom_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class LlmRoot:
    provider: Provider = "ocean"
    model: str = "global.anthropic.claude-sonnet-4-6"
    ocean: dict[str, Any] = field(default_factory=dict)
    ollama: dict[str, Any] = field(default_factory=dict)
    channels: LlmChannels = field(default_factory=LlmChannels)
    temperature: float | None = None


@dataclass
class ToolsPolicy:
    # WeCom userids that may use tools; empty = no one on WeCom gets tools.
    # Local channel always gets tools.
    owner_userids: list[str] = field(default_factory=list)


@dataclass
class AgentConfig:
    llm: LlmRoot = field(default_factory=LlmRoot)
    reply: ReplyPolicy = field(default_factory=ReplyPolicy)
    identity: dict[str, Any] = field(default_factory=dict)
    sections: dict[str, SectionSpec] = field(default_factory=dict)
    tools_policy: ToolsPolicy = field(default_factory=ToolsPolicy)
    skills_dir: str = "skills"
    transcripts_dir: str = "data/transcripts"
    memory_dir: str = "data/memory"
    history_limit: int = 40
    wecom_mention: str | None = None  # display name used in group @mentions, e.g. "Baby Jasmine"
