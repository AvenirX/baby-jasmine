from __future__ import annotations

from pathlib import Path

import yaml

from baby_jasmine.config_loader import (
    load_agent_config,
    resolve_llm,
    section_enabled,
    section_template,
    wecom_force_assistant_text,
)
from baby_jasmine.config_models import SectionChannels, SectionSpec
from baby_jasmine.pi_stream.ocean import _normalize_url


def test_resolve_llm_local_override(tmp_path: Path) -> None:
    cfg_path = tmp_path / "agent.yaml"
    cfg_path.write_text(
        yaml.dump(
            {
                "llm": {
                    "provider": "ocean",
                    "model": "global.anthropic.claude-sonnet-4-6",
                    "channels": {
                        "local": {"provider": "ollama", "model": "mistral"},
                        "wecom": {
                            "provider": "ocean",
                            "model": "global.anthropic.claude-sonnet-4-6",
                        },
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    cfg = load_agent_config(cfg_path)
    r = resolve_llm(cfg, channel="local", wecom_userid=None)
    assert r.provider == "ollama"
    assert r.model == "mistral"


def test_resolve_llm_wecom_user_override(tmp_path: Path) -> None:
    cfg_path = tmp_path / "agent.yaml"
    cfg_path.write_text(
        yaml.dump(
            {
                "llm": {
                    "provider": "ocean",
                    "model": "m1",
                    "channels": {
                        "local": {},
                        "wecom": {
                            "provider": "ocean",
                            "model": "m2",
                            "overrides": {"u1": {"provider": "ollama", "model": "qwen"}},
                        },
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    cfg = load_agent_config(cfg_path)
    r0 = resolve_llm(cfg, channel="wecom", wecom_userid=None)
    assert r0.model == "m2"
    r1 = resolve_llm(cfg, channel="wecom", wecom_userid="u1")
    assert r1.provider == "ollama"
    assert r1.model == "qwen"


def test_section_enabled_wecom_override() -> None:
    spec = SectionSpec(
        template="t.md",
        channels=SectionChannels(
            wecom_enabled=True,
            wecom_overrides={"wx": {"enabled": False}},
        ),
    )
    assert section_enabled(spec, channel="wecom", wecom_userid="wx") is False
    assert section_enabled(spec, channel="wecom", wecom_userid="other") is True


def test_section_template_wecom_override() -> None:
    spec = SectionSpec(
        template="templates/default.md",
        channels=SectionChannels(
            wecom_overrides={"u1": {"template": "templates/override.md"}},
        ),
    )
    assert section_template(spec, channel="local", wecom_userid="u1") == "templates/default.md"
    assert section_template(spec, channel="wecom", wecom_userid="u1") == "templates/override.md"
    assert section_template(spec, channel="wecom", wecom_userid="other") == "templates/default.md"


def test_load_agent_config_personality_wecom_template_override(tmp_path: Path) -> None:
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "p.md").write_text("BASE", encoding="utf-8")
    (tmp_path / "templates" / "o.md").write_text("OVERRIDE", encoding="utf-8")
    cfg_path = tmp_path / "agent.yaml"
    cfg_path.write_text(
        yaml.dump(
            {
                "sections": {
                    "personality": {
                        "template": "templates/p.md",
                        "channels": {
                            "wecom": {
                                "overrides": {"wxid": {"template": "templates/o.md"}},
                            }
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    cfg = load_agent_config(cfg_path)
    p = cfg.sections["personality"]
    assert section_template(p, channel="wecom", wecom_userid="wxid") == "templates/o.md"
    assert section_template(p, channel="wecom", wecom_userid="x") == "templates/p.md"


def test_wecom_force_assistant_parse(tmp_path: Path) -> None:
    cfg_path = tmp_path / "agent.yaml"
    cfg_path.write_text(
        yaml.dump(
            {
                "reply": {
                    "max_emojis": 4,
                    "channels": {
                        "wecom": {
                            "overrides": {
                                "user123": {"force_assistant": "🧸"},
                            }
                        }
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    cfg = load_agent_config(cfg_path)
    assert wecom_force_assistant_text(cfg.reply, "user123") == "🧸"
    assert wecom_force_assistant_text(cfg.reply, "other") is None
    assert wecom_force_assistant_text(cfg.reply, None) is None


def test_normalize_url_appends_path_for_origin_only_gateway() -> None:
    assert _normalize_url("https://ocean.example.com:7799") == (
        "https://ocean.example.com:7799/ocean/v1.0/proxy/ai"
    )


def test_normalize_url_leaves_full_gateway_url_unchanged() -> None:
    full = "https://ocean.example.com:7799/ocean/v1.0/proxy/ai"
    assert _normalize_url(full) == full
