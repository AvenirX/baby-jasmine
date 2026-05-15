from __future__ import annotations

import inspect
import json
from collections.abc import Callable
from pathlib import Path

from pi_agent_core import ImageContent, Model, SimpleStreamOptions, TextContent

from baby_jasmine.agent_sessions import AgentSessionManager
from baby_jasmine.config_loader import is_tool_owner, resolve_llm, wecom_force_assistant_text
from baby_jasmine.config_models import AgentConfig, Channel
from baby_jasmine.context.builder import build_system_prompt
from baby_jasmine.context.post import (
    EMOJI_ONLY_REPAIR_SYSTEM,
    REPAIR_SYSTEM_PROMPT,
    cap_emojis,
    emoji_only_repair_message,
    repair_user_message,
    should_run_repair,
)
from baby_jasmine.memory.transcripts import JsonlHistory
from baby_jasmine.pi_stream.factory import create_stream_fn
from baby_jasmine.tools.registry import list_tools


async def run_turn(
    *,
    cfg: AgentConfig,
    project_root: Path,
    history_store: JsonlHistory,
    sessions: AgentSessionManager,
    session_key: str,
    channel: Channel,
    wecom_userid: str | None,
    group_id: str | None = None,
    user_text: str,
    user_images: list[ImageContent] | None = None,
    cli_provider: str | None = None,
    cli_model: str | None = None,
    on_delta: Callable[[str], None] | None = None,
    on_stream_reset: Callable[[], None] | None = None,
) -> str:
    resolved = resolve_llm(
        cfg,
        channel=channel,
        wecom_userid=wecom_userid,
        cli_provider=cli_provider,
        cli_model=cli_model,
    )
    meta = {"llm.provider": resolved.provider, "llm.model": resolved.model}

    history_store.append(
        session_key=session_key,
        channel=channel,
        role="user",
        text=user_text,
        wecom_userid=wecom_userid,
        meta=meta,
    )

    policy = cfg.reply
    forced = wecom_force_assistant_text(policy, wecom_userid) if channel == "wecom" else None

    stream_fn = None
    if forced is not None:
        if on_delta:
            on_delta(forced)
        draft = forced
    else:
        stream_fn = create_stream_fn(resolved)
        model = Model(api=resolved.provider, provider=resolved.provider, id=resolved.model)
        tool_owner = is_tool_owner(cfg, channel=channel, wecom_userid=wecom_userid)
        system = build_system_prompt(
            cfg,
            project_root=project_root,
            channel=channel,
            wecom_userid=wecom_userid,
            group_id=group_id,
            has_tools=tool_owner,
        )
        tools = list_tools() if tool_owner else []

        agent = sessions.get_or_create(
            session_key,
            history_store=history_store,
            history_limit=cfg.history_limit,
            stream_fn=stream_fn,
            model=model,
        )
        agent.set_system_prompt(system)
        agent.set_tools(tools)

        def on_event(event) -> None:
            if event.type == "tool_execution_start":
                if on_stream_reset:
                    on_stream_reset()
                tool_payload = {
                    "id": event.tool_call_id,
                    "name": event.tool_name,
                    "input": event.args or {},
                }
                print(f"[tool_use] {json.dumps(tool_payload, ensure_ascii=False)}", flush=True)
                history_store.append(
                    session_key=session_key,
                    channel=channel,
                    role="tool_use",
                    text=json.dumps(tool_payload, ensure_ascii=False),
                    wecom_userid=wecom_userid,
                    meta=meta,
                )
            elif event.type == "tool_execution_end":
                result_text = (
                    "".join(c.text for c in event.result.content if isinstance(c, TextContent))
                    if event.result
                    else ""
                )
                print(
                    f"[tool_result] id={event.tool_call_id} error={event.is_error}"
                    f" {result_text[:200]!r}",
                    flush=True,
                )
                history_store.append(
                    session_key=session_key,
                    channel=channel,
                    role="tool_result",
                    text=result_text,
                    wecom_userid=wecom_userid,
                    meta={**meta, "tool_use_id": event.tool_call_id, "is_error": event.is_error},
                )
            elif event.type == "message_update" and on_delta:
                sub = event.assistant_message_event
                if sub is not None and sub.type == "text_delta":
                    on_delta(sub.delta)

        unsubscribe = agent.subscribe(on_event)
        try:
            await agent.prompt(user_text, images=user_images or None)
        finally:
            unsubscribe()

        messages = agent.state.messages
        last = messages[-1] if messages else None
        if last is not None and getattr(last, "role", None) == "assistant":
            draft = "".join(c.text for c in last.content if isinstance(c, TextContent))
        else:
            draft = ""

    if should_run_repair(draft, policy) and stream_fn is not None:
        from pi_agent_core import AgentContext, UserMessage

        if policy.emoji_only:
            sys_prompt = EMOJI_ONLY_REPAIR_SYSTEM
            user_msg = emoji_only_repair_message(user_text=user_text, draft=draft)
        else:
            sys_prompt = REPAIR_SYSTEM_PROMPT
            user_msg = repair_user_message(
                user_text=user_text, draft=draft, max_emojis=policy.max_emojis
            )

        repair_context = AgentContext(
            system_prompt=sys_prompt,
            messages=[UserMessage(content=[TextContent(text=user_msg)])],
            tools=[],
        )
        model = Model(api=resolved.provider, provider=resolved.provider, id=resolved.model)
        stream_result = stream_fn(model, repair_context, SimpleStreamOptions())
        if inspect.isawaitable(stream_result):
            stream_result = await stream_result
        async for _ in stream_result["events"]:
            pass
        repair_msg = await stream_result["result"]()
        draft = "".join(c.text for c in repair_msg.content if isinstance(c, TextContent))

    full = cap_emojis(draft, policy.max_emojis)
    history_store.append(
        session_key=session_key,
        channel=channel,
        role="assistant",
        text=full,
        wecom_userid=wecom_userid,
        meta=meta,
    )
    return full
