from __future__ import annotations

from pathlib import Path

import yaml

from baby_jasmine.config_loader import load_agent_config
from baby_jasmine.context.builder import build_system_prompt


def test_build_system_prompt_wecom_uses_per_user_personality_template(tmp_path: Path) -> None:
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "base.md").write_text("P_BASE", encoding="utf-8")
    (tmp_path / "templates" / "u.md").write_text("P_USER", encoding="utf-8")
    (tmp_path / "agent.yaml").write_text(
        yaml.dump(
            {
                "identity": {"inline": "ID"},
                "sections": {
                    "personality": {
                        "template": "templates/base.md",
                        "channels": {
                            "wecom": {
                                "overrides": {"user_abc": {"template": "templates/u.md"}},
                            }
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    cfg = load_agent_config(tmp_path / "agent.yaml")
    out = build_system_prompt(cfg, project_root=tmp_path, channel="wecom", wecom_userid="user_abc")
    assert "P_USER" in out
    assert "P_BASE" not in out
    out_default = build_system_prompt(
        cfg, project_root=tmp_path, channel="wecom", wecom_userid="other"
    )
    assert "P_BASE" in out_default
    assert "P_USER" not in out_default


def test_build_system_prompt_wecom_append_merges_base_and_override(tmp_path: Path) -> None:
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "base.md").write_text("P_BASE", encoding="utf-8")
    (tmp_path / "templates" / "add.md").write_text("P_ADD", encoding="utf-8")
    (tmp_path / "agent.yaml").write_text(
        yaml.dump(
            {
                "identity": {"inline": "ID"},
                "sections": {
                    "personality": {
                        "template": "templates/base.md",
                        "channels": {
                            "wecom": {
                                "overrides": {
                                    "u1": {
                                        "template": "templates/add.md",
                                        "template_merge": "append",
                                    }
                                }
                            }
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    cfg = load_agent_config(tmp_path / "agent.yaml")
    out = build_system_prompt(cfg, project_root=tmp_path, channel="wecom", wecom_userid="u1")
    assert "P_BASE" in out
    assert "P_ADD" in out
    assert out.index("P_BASE") < out.index("P_ADD")
