from __future__ import annotations

from pathlib import Path

_transcripts_root: Path | None = None
_memory_root: Path | None = None


def init_memory(transcripts_root: Path, memory_root: Path) -> None:
    global _transcripts_root, _memory_root
    _transcripts_root = transcripts_root
    _memory_root = memory_root
    (memory_root / "persons").mkdir(parents=True, exist_ok=True)


def get_transcripts_root() -> Path:
    if _transcripts_root is None:
        raise RuntimeError("Memory not initialized; call init_memory() first")
    return _transcripts_root


def get_memory_root() -> Path:
    if _memory_root is None:
        raise RuntimeError("Memory not initialized; call init_memory() first")
    return _memory_root


def get_self_context_path() -> Path:
    if _memory_root is None:
        raise RuntimeError("Memory not initialized; call init_memory() first")
    return _memory_root.parent / "self.md"
