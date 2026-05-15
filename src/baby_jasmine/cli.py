from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from baby_jasmine.loop.runner import async_main


def main_sync() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    parser = argparse.ArgumentParser(description="Baby Jasmine — local + WeCom agent CLI")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/agent.yaml"),
        help="Path to agent.yaml",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Project root for resolving templates and data/",
    )
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--local", action="store_true", help="Stdin/stdout chat loop")
    g.add_argument("--wecom", action="store_true", help="WeCom WebSocket bot (needs [wecom] extra)")
    g.add_argument("--all", action="store_true", help="Run local and WeCom in parallel")
    parser.add_argument(
        "--provider",
        choices=("ocean", "ollama"),
        default=None,
        help="Override LLM provider for this process",
    )
    parser.add_argument("--model", type=str, default=None, help="Override model id / Ollama tag")
    args = parser.parse_args()

    if args.all:
        mode = "all"
    elif args.wecom:
        mode = "wecom"
    else:
        mode = "local"

    cfg_path = args.project_root / args.config if not args.config.is_absolute() else args.config
    if not cfg_path.is_file():
        print(f"Config not found: {cfg_path}", file=sys.stderr)
        sys.exit(1)

    try:
        asyncio.run(
            async_main(
                mode=mode,
                config_path=cfg_path,
                project_root=args.project_root.resolve(),
                cli_provider=args.provider,
                cli_model=args.model,
            )
        )
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
