from __future__ import annotations

import asyncio
from pathlib import Path

from baby_jasmine.agent_sessions import AgentSessionManager
from baby_jasmine.channels.local import run_local_loop
from baby_jasmine.channels.wecom import run_wecom_loop
from baby_jasmine.config_loader import load_agent_config
from baby_jasmine.memory.context import init_memory
from baby_jasmine.memory.transcripts import JsonlHistory
from baby_jasmine.tools import builtin as _builtin_tools  # noqa: F401 — side-effect registers


async def async_main(
    *,
    mode: str,
    config_path: Path,
    project_root: Path,
    cli_provider: str | None,
    cli_model: str | None,
) -> None:
    cfg = load_agent_config(config_path)
    history = JsonlHistory(project_root / cfg.transcripts_dir)
    init_memory(
        transcripts_root=project_root / cfg.transcripts_dir,
        memory_root=project_root / cfg.memory_dir,
    )
    sessions = AgentSessionManager()

    if mode == "local":
        await run_local_loop(
            cfg=cfg,
            project_root=project_root,
            history=history,
            sessions=sessions,
            cli_provider=cli_provider,
            cli_model=cli_model,
        )
    elif mode == "wecom":
        await run_wecom_loop(
            cfg=cfg,
            project_root=project_root,
            history=history,
            sessions=sessions,
            cli_provider=cli_provider,
            cli_model=cli_model,
        )
    else:
        await asyncio.gather(
            run_local_loop(
                cfg=cfg,
                project_root=project_root,
                history=history,
                sessions=sessions,
                cli_provider=cli_provider,
                cli_model=cli_model,
            ),
            run_wecom_loop(
                cfg=cfg,
                project_root=project_root,
                history=history,
                sessions=sessions,
                cli_provider=cli_provider,
                cli_model=cli_model,
            ),
        )
