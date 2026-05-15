from __future__ import annotations

from pi_agent_core import Agent, AgentOptions, Model

from baby_jasmine.memory.transcripts import JsonlHistory


class AgentSessionManager:
    """Cache of one Agent per session_key — openclaw's SessionManager pattern."""

    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}

    def get_or_create(
        self,
        session_key: str,
        *,
        history_store: JsonlHistory,
        history_limit: int,
        stream_fn,
        model: Model,
    ) -> Agent:
        if session_key not in self._agents:
            agent = Agent(AgentOptions(stream_fn=stream_fn))
            agent.set_model(model)
            msgs = history_store.load_recent_messages(session_key, limit=history_limit)
            if msgs:
                agent.replace_messages(msgs)
            self._agents[session_key] = agent
        else:
            agent = self._agents[session_key]
            agent.stream_fn = stream_fn
            agent.set_model(model)
        return agent
