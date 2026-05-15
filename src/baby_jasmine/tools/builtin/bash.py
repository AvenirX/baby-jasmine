from __future__ import annotations

import asyncio
import platform
import sys
from typing import Any

from baby_jasmine.tools.registry import tool

_TIMEOUT = 30

_SHELL_NOTE = (
    "Shell is cmd.exe (Windows) — use Windows syntax."
    if sys.platform == "win32"
    else f"Shell is {platform.system()} bash/sh — use POSIX syntax."
)


@tool(
    name="bash",
    description=(f"Run a shell command and return stdout + stderr. {_SHELL_NOTE}"),
    input_schema={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to execute"},
            "timeout": {
                "type": "number",
                "description": f"Timeout in seconds (default {_TIMEOUT})",
            },
        },
        "required": ["command"],
        "additionalProperties": False,
    },
)
async def bash(args: dict[str, Any]) -> str:
    command = args["command"]
    timeout = float(args.get("timeout") or _TIMEOUT)
    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        return f"[timeout after {timeout}s]"
    output = stdout.decode(errors="replace").rstrip()
    rc = proc.returncode
    if rc != 0:
        return f"[exit {rc}]\n{output}" if output else f"[exit {rc}]"
    return output or "[no output]"
