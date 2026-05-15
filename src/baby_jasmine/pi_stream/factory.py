from __future__ import annotations

from baby_jasmine.config_models import ResolvedLlmConfig
from baby_jasmine.pi_stream.ocean import make_ocean_stream_fn
from baby_jasmine.pi_stream.ollama import make_ollama_stream_fn


def create_stream_fn(resolved: ResolvedLlmConfig):
    """Return the appropriate StreamFn for the resolved LLM config."""
    if resolved.provider == "ollama":
        return make_ollama_stream_fn(resolved)
    return make_ocean_stream_fn(resolved)
