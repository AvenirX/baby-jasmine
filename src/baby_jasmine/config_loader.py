from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import yaml

from baby_jasmine.config_models import (
    AgentConfig,
    Channel,
    LlmChannels,
    LlmRoot,
    ReplyPolicy,
    ResolvedLlmConfig,
    SectionChannels,
    SectionSpec,
    ToolsPolicy,
)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _parse_section(name: str, raw: dict[str, Any]) -> SectionSpec:
    ch = raw.get("channels") or {}
    loc = ch.get("local") or {}
    wc = ch.get("wecom") or {}
    wo = (wc.get("overrides") or {}) if isinstance(wc.get("overrides"), dict) else {}
    return SectionSpec(
        template=str(raw.get("template", f"prompt/{name}.md")),
        channels=SectionChannels(
            local_enabled=bool(loc.get("enabled", True)),
            wecom_enabled=bool(wc.get("enabled", True)),
            wecom_overrides={str(k): dict(v) for k, v in wo.items()},
        ),
    )


def _parse_llm_channels(raw: dict[str, Any]) -> LlmChannels:
    ch = raw.get("channels") or {}
    loc = ch.get("local") or {}
    wc = ch.get("wecom") or {}
    wo = (wc.get("overrides") or {}) if isinstance(wc.get("overrides"), dict) else {}
    return LlmChannels(
        local=dict(loc) if isinstance(loc, dict) else {},
        wecom={k: v for k, v in wc.items() if k != "overrides"},
        wecom_overrides={str(k): dict(v) for k, v in wo.items()},
    )


def _parse_reply(raw: Any) -> ReplyPolicy:
    if not isinstance(raw, dict):
        return ReplyPolicy()
    rep = raw.get("repair") or {}
    rep_dict = rep if isinstance(rep, dict) else {}
    rch = raw.get("channels") or {}
    rwc = rch.get("wecom") or {} if isinstance(rch, dict) else {}
    rwo = (rwc.get("overrides") or {}) if isinstance(rwc.get("overrides"), dict) else {}
    return ReplyPolicy(
        max_emojis=int(raw.get("max_emojis", 4)),
        repair_enabled=bool(rep_dict.get("enabled", False)),
        emoji_only=bool(rep_dict.get("emoji_only", False)),
        wecom_overrides={str(k): dict(v) for k, v in rwo.items()},
    )


def _parse_tools(raw: Any) -> ToolsPolicy:
    if not isinstance(raw, dict):
        return ToolsPolicy()
    ids = raw.get("owner_userids") or []
    if not isinstance(ids, list):
        ids = [ids] if ids else []
    return ToolsPolicy(owner_userids=[str(x) for x in ids])


def is_tool_owner(
    cfg: AgentConfig,
    *,
    channel: Channel,
    wecom_userid: str | None,
) -> bool:
    """Local channel always has tools; WeCom requires userid in owner_userids."""
    if channel == "local":
        return True
    return bool(wecom_userid and wecom_userid in cfg.tools_policy.owner_userids)


def wecom_force_assistant_text(reply: ReplyPolicy, wecom_userid: str | None) -> str | None:
    """If set for this WeCom user, the assistant message is this text (no LLM call)."""
    if not wecom_userid:
        return None
    o = reply.wecom_overrides.get(wecom_userid) or {}
    t = o.get("force_assistant")
    if isinstance(t, str) and t.strip():
        return t
    return None


def _parse_llm_root(raw: dict[str, Any]) -> LlmRoot:
    prov = raw.get("provider", "ocean")
    if prov not in ("ocean", "ollama"):
        prov = "ocean"
    return LlmRoot(
        provider=prov,  # type: ignore[arg-type]
        model=str(raw.get("model", "global.anthropic.claude-sonnet-4-6")),
        ocean=dict(raw.get("ocean") or {}),
        ollama=dict(raw.get("ollama") or {}),
        channels=_parse_llm_channels(raw),
        temperature=raw.get("temperature"),
    )


def load_agent_config(path: Path) -> AgentConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    llm_raw = data.get("llm") or {}
    sections_raw = data.get("sections") or {}
    sections: dict[str, SectionSpec] = {}
    for name, sraw in sections_raw.items():
        if isinstance(sraw, dict):
            sections[str(name)] = _parse_section(str(name), sraw)
    return AgentConfig(
        llm=_parse_llm_root(llm_raw),
        reply=_parse_reply(data.get("reply")),
        identity=dict(data.get("identity") or {}),
        sections=sections,
        tools_policy=_parse_tools(data.get("tools") or {}),
        skills_dir=str(data.get("skills_dir", "skills")),
        transcripts_dir=str(data.get("transcripts_dir", "data/transcripts")),
        history_limit=int(data.get("history_limit", 40)),
    )


def resolve_llm(
    cfg: AgentConfig,
    *,
    channel: Channel,
    wecom_userid: str | None,
    cli_provider: str | None = None,
    cli_model: str | None = None,
) -> ResolvedLlmConfig:
    base: dict[str, Any] = {
        "provider": cfg.llm.provider,
        "model": cfg.llm.model,
        "ocean": dict(cfg.llm.ocean),
        "ollama": dict(cfg.llm.ollama),
        "temperature": cfg.llm.temperature,
    }
    if channel == "local":
        merged = _deep_merge(base, dict(cfg.llm.channels.local))
    else:
        merged = _deep_merge(base, dict(cfg.llm.channels.wecom))
        if wecom_userid and wecom_userid in cfg.llm.channels.wecom_overrides:
            merged = _deep_merge(merged, dict(cfg.llm.channels.wecom_overrides[wecom_userid]))

    if cli_provider in ("ocean", "ollama"):
        merged["provider"] = cli_provider
    if cli_model:
        merged["model"] = cli_model

    prov = merged.get("provider", "ocean")
    if prov not in ("ocean", "ollama"):
        prov = "ocean"
    ocean = merged.get("ocean") or {}
    ollama = merged.get("ollama") or {}
    return ResolvedLlmConfig(
        provider=prov,  # type: ignore[arg-type]
        model=str(merged.get("model", "")),
        ocean_gateway_url=ocean.get("gateway_url") or os.environ.get("OCEAN_GATEWAY_URL"),
        ocean_scene_id=ocean.get("scene_id") or os.environ.get("OCEAN_SCENE_ID"),
        ollama_base_url=ollama.get("base_url") or os.environ.get("OLLAMA_BASE_URL"),
        temperature=(
            merged.get("temperature")
            if merged.get("temperature") is not None
            else cfg.llm.temperature
        ),
    )


def section_enabled(
    spec: SectionSpec,
    *,
    channel: Channel,
    wecom_userid: str | None,
) -> bool:
    if channel == "local":
        return spec.channels.local_enabled
    if wecom_userid and wecom_userid in spec.channels.wecom_overrides:
        o = spec.channels.wecom_overrides[wecom_userid]
        if "enabled" in o:
            return bool(o["enabled"])
    return spec.channels.wecom_enabled


def section_template(
    spec: SectionSpec,
    *,
    channel: Channel,
    wecom_userid: str | None,
) -> str:
    """Path to the section markdown, relative to project root.

    WeCom per-user `channels.wecom.overrides.<userid>.template` overrides the
    section default when set to a non-empty string.
    """
    if channel == "wecom" and wecom_userid and wecom_userid in spec.channels.wecom_overrides:
        o = spec.channels.wecom_overrides[wecom_userid]
        t = o.get("template")
        if isinstance(t, str) and t.strip():
            return t.strip()
    return spec.template


def wecom_template_merge_is_append(
    spec: SectionSpec,
    *,
    channel: Channel,
    wecom_userid: str | None,
) -> bool:
    """WeCom per-user `template_merge: append` keeps `spec.template` and appends the override file.

    Default (replace) matches prior behavior: override `template` alone replaces the section body.
    """
    if channel != "wecom" or not wecom_userid or wecom_userid not in spec.channels.wecom_overrides:
        return False
    o = spec.channels.wecom_overrides[wecom_userid]
    t = o.get("template")
    if not isinstance(t, str) or not t.strip():
        return False
    return str(o.get("template_merge", "replace") or "replace") == "append"


def wecom_sender_label(cfg: AgentConfig, wecom_userid: str | None) -> str | None:
    """Return the configured display_name for a WeCom user (e.g. 'your father 🧸'), or None."""
    if not wecom_userid:
        return None
    personality = cfg.sections.get("personality")
    if not personality:
        return None
    o = personality.channels.wecom_overrides.get(wecom_userid) or {}
    label = o.get("display_name")
    return str(label).strip() if isinstance(label, str) and label.strip() else None


def read_template(project_root: Path, relative_path: str) -> str:
    p = project_root / relative_path
    if not p.is_file():
        return ""
    return p.read_text(encoding="utf-8").strip()
