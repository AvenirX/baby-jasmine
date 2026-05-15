from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from baby_jasmine.agent_sessions import AgentSessionManager
from baby_jasmine.config_models import AgentConfig
from baby_jasmine.loop.turn import run_turn
from baby_jasmine.memory.transcripts import JsonlHistory


async def _read_line(prompt: str) -> str:
    sys.stdout.write(prompt)
    sys.stdout.flush()
    return await asyncio.to_thread(sys.stdin.readline)


async def run_local_loop(
    *,
    cfg: AgentConfig,
    project_root: Path,
    history: JsonlHistory,
    sessions: AgentSessionManager,
    cli_provider: str | None,
    cli_model: str | None,
) -> None:
    session_key = "local"
    while True:
        line = await _read_line("you> ")
        if not line:
            break
        user_text = line.rstrip("\n\r")
        if not user_text:
            continue
        if user_text.lower() in ("/quit", "/exit"):
            break

        def print_delta(d: str) -> None:
            sys.stdout.write(d)
            sys.stdout.flush()

        sys.stdout.write("assistant> ")
        sys.stdout.flush()
        await run_turn(
            cfg=cfg,
            project_root=project_root,
            history_store=history,
            sessions=sessions,
            session_key=session_key,
            channel="local",
            wecom_userid=None,
            user_text=user_text,
            cli_provider=cli_provider,
            cli_model=cli_model,
            on_delta=print_delta,
        )
        sys.stdout.write("\n")
        sys.stdout.flush()
