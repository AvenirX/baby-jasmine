from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import yaml
from pi_agent_core import AssistantMessage, StreamDoneEvent, TextContent

from baby_jasmine.agent_sessions import AgentSessionManager
from baby_jasmine.config_loader import load_agent_config
from baby_jasmine.config_models import AgentConfig, ReplyPolicy
from baby_jasmine.context.post import cap_emojis, count_emoji_units, should_run_repair
from baby_jasmine.loop.turn import run_turn
from baby_jasmine.memory.transcripts import JsonlHistory


def _make_text_stream_fn(texts: list[str]):
    call_index = [0]

    def stream_fn(model, context, options):
        text = texts[call_index[0]]
        call_index[0] += 1
        msg = AssistantMessage(content=[TextContent(text=text)], stop_reason="stop")

        async def gen():
            yield StreamDoneEvent(reason="stop", message=msg)

        async def result():
            return msg

        return {"events": gen(), "result": result}

    stream_fn._calls = call_index
    return stream_fn


def test_count_emoji_units_plain_text() -> None:
    assert count_emoji_units("hello") == 0


def test_count_emoji_units_mixed() -> None:
    assert count_emoji_units("a😀b🎉c") == 2


def test_count_emoji_zwj_family_one_unit() -> None:
    s = "x 👨‍👩‍👧 y"
    assert count_emoji_units(s) == 1


def test_cap_emojis_keeps_first_n() -> None:
    assert cap_emojis("a😀b🎉c✨", 2) == "a😀b🎉c"
    assert count_emoji_units(cap_emojis("a😀b🎉c✨", 2)) == 2


def test_cap_emojis_zero_strips_all() -> None:
    out = cap_emojis("hi 😀 there 🎉", 0)
    assert out == "hi  there "
    assert count_emoji_units(out) == 0


def test_should_run_repair() -> None:
    p = ReplyPolicy(max_emojis=2, repair_enabled=True)
    assert should_run_repair("a😀😀😀", p) is True
    assert should_run_repair("a😀😀", p) is False
    p2 = ReplyPolicy(max_emojis=2, repair_enabled=False)
    assert should_run_repair("a😀😀😀", p2) is False


def test_load_agent_config_reply(tmp_path: Path) -> None:
    cfg_path = tmp_path / "agent.yaml"
    cfg_path.write_text(
        yaml.dump(
            {
                "reply": {"max_emojis": 3, "repair": {"enabled": True}},
                "llm": {"provider": "ollama", "model": "m"},
            }
        ),
        encoding="utf-8",
    )
    cfg = load_agent_config(cfg_path)
    assert cfg.reply.max_emojis == 3
    assert cfg.reply.repair_enabled is True


def test_run_turn_caps_without_repair(tmp_path: Path) -> None:
    cfg = AgentConfig()
    cfg.reply = ReplyPolicy(max_emojis=2, repair_enabled=False)
    project_root = tmp_path
    (project_root / "templates").mkdir()
    (project_root / "templates" / "identity.md").write_text("id", encoding="utf-8")
    hist = JsonlHistory(root=tmp_path / "t")
    sessions = AgentSessionManager()
    fake_fn = _make_text_stream_fn(["hello 😀😀😀"])

    async def _run() -> str:
        with patch("baby_jasmine.loop.turn.create_stream_fn", return_value=fake_fn):
            return await run_turn(
                cfg=cfg,
                project_root=project_root,
                history_store=hist,
                sessions=sessions,
                session_key="s1",
                channel="local",
                wecom_userid=None,
                user_text="u",
            )

    out = asyncio.run(_run())
    assert out == "hello 😀😀"
    assert count_emoji_units(out) == 2
    assert fake_fn._calls[0] == 1


def test_run_turn_repair_then_cap(tmp_path: Path) -> None:
    cfg = AgentConfig()
    cfg.reply = ReplyPolicy(max_emojis=2, repair_enabled=True)
    project_root = tmp_path
    (project_root / "templates").mkdir()
    (project_root / "templates" / "identity.md").write_text("id", encoding="utf-8")
    hist = JsonlHistory(root=tmp_path / "t")
    sessions = AgentSessionManager()
    # First call: too many emojis → triggers repair; second call: repair response
    fake_fn = _make_text_stream_fn(["x 😀😀😀", "x 😀😀😀"])

    async def _run() -> str:
        with patch("baby_jasmine.loop.turn.create_stream_fn", return_value=fake_fn):
            return await run_turn(
                cfg=cfg,
                project_root=project_root,
                history_store=hist,
                sessions=sessions,
                session_key="s1",
                channel="local",
                wecom_userid=None,
                user_text="u",
            )

    out = asyncio.run(_run())
    assert out == "x 😀😀"
    assert count_emoji_units(out) == 2
    assert fake_fn._calls[0] == 2
