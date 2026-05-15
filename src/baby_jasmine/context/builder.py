from __future__ import annotations

from pathlib import Path

from baby_jasmine.config_loader import (
    read_template,
    section_enabled,
    section_template,
    wecom_sender_label,
    wecom_template_merge_is_append,
)
from baby_jasmine.config_models import AgentConfig, Channel


def _join_template_bodies(base: str, addendum: str) -> str:
    a, b = base.strip(), addendum.strip()
    if not a:
        return b
    if not b:
        return a
    return f"{a}\n\n{b}"


def _load_skills(project_root: Path, skills_dir: str) -> str:
    base = project_root / skills_dir
    if not base.is_dir():
        return ""
    blocks: list[str] = []
    for skill_md in sorted(base.glob("*/SKILL.md")):
        name = skill_md.parent.name
        raw = skill_md.read_text(encoding="utf-8").strip()
        # Strip YAML frontmatter if present
        if raw.startswith("---"):
            end = raw.find("---", 3)
            body = raw[end + 3 :].strip() if end != -1 else raw
        else:
            body = raw
        if body:
            blocks.append(f'<skill name="{name}">\n{body}\n</skill>')
    return "\n\n".join(blocks)


def build_system_prompt(
    cfg: AgentConfig,
    *,
    project_root: Path,
    channel: Channel,
    wecom_userid: str | None,
    group_id: str | None = None,
    has_tools: bool = True,
) -> str:
    parts: list[str] = []
    ident = cfg.identity
    if isinstance(ident.get("inline"), str) and ident["inline"].strip():
        parts.append(ident["inline"].strip())
    elif ident.get("template"):
        text = read_template(project_root, str(ident["template"]))
        if text:
            parts.append(text)
    for name, spec in cfg.sections.items():
        if not section_enabled(spec, channel=channel, wecom_userid=wecom_userid):
            continue
        if name == "personality" and wecom_template_merge_is_append(
            spec, channel=channel, wecom_userid=wecom_userid
        ):
            base = read_template(project_root, spec.template)
            rel = section_template(spec, channel=channel, wecom_userid=wecom_userid)
            addendum = read_template(project_root, rel)
            body = _join_template_bodies(base, addendum)
        else:
            rel = section_template(spec, channel=channel, wecom_userid=wecom_userid)
            body = read_template(project_root, rel)
        if body:
            parts.append(body)
    skills_block = _load_skills(project_root, cfg.skills_dir)
    if skills_block:
        parts.append(skills_block)

    self_ctx_path = project_root / Path(cfg.memory_dir).parent / "self.md"
    if self_ctx_path.is_file():
        body = self_ctx_path.read_text(encoding="utf-8").strip()
        if body:
            parts.append(f"<self_context>\n{body}\n</self_context>")

    # WeCom: memory privacy rules + per-request conversation context
    if channel == "wecom":
        privacy_md = project_root / "prompt" / "memory_privacy.md"
        if privacy_md.is_file():
            body = privacy_md.read_text(encoding="utf-8").strip()
            if body:
                parts.append(body)
        display_name = wecom_sender_label(cfg, wecom_userid)
        context_block = _build_wecom_context_block(
            wecom_userid, group_id, display_name, has_tools=has_tools
        )
        if context_block:
            parts.append(context_block)

    return "\n\n".join(parts).strip()


def _build_wecom_context_block(
    wecom_userid: str | None,
    group_id: str | None,
    display_name: str | None = None,
    has_tools: bool = True,
) -> str:
    if not wecom_userid:
        return ""
    sender = f"{display_name} (`{wecom_userid}`)" if display_name else f"`{wecom_userid}`"
    lines = ["## Current Conversation Context"]
    if group_id:
        lines.append(f"- Chat type: group (ID: `{group_id}`)")
        lines.append(f"- Sender: {sender}")
        if has_tools:
            lines.append("")
            lines.append(
                f'Before responding, call `recall_person` with `wecom_userid="{wecom_userid}"` '
                f'and `current_context="group"` to recall what you know about this person.'
            )
    else:
        lines.append("- Chat type: private")
        lines.append(f"- Sender: {sender}")
        if has_tools:
            lines.append("")
            lines.append(
                f'Optionally call `recall_person` with `wecom_userid="{wecom_userid}"` '
                f'and `current_context="private"` if context about this person would help.'
            )
    return "\n".join(lines)
