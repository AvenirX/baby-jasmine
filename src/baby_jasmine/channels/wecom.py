from __future__ import annotations

import asyncio
import base64
import logging
import os
import re as _re
import uuid
from pathlib import Path

from baby_jasmine.agent_sessions import AgentSessionManager
from baby_jasmine.config_models import AgentConfig
from baby_jasmine.loop.turn import run_turn
from baby_jasmine.memory.transcripts import JsonlHistory
from baby_jasmine.utils.network import get_monitor

try:
    from wecom_aibot import WSClient, WSClientOptions
    from wecom_aibot.logger import DefaultLogger as _WeComDefaultLogger
    from wecom_aibot.types.message import (
        FileMessage,
        ImageMessage,
        MixedMessage,
        TextMessage,
        VoiceMessage,
    )
except ImportError:
    WSClient = None  # type: ignore[misc, assignment]
    WSClientOptions = None  # type: ignore[misc, assignment]
    TextMessage = None  # type: ignore[misc, assignment]
    ImageMessage = None  # type: ignore[misc, assignment]
    FileMessage = None  # type: ignore[misc, assignment]
    VoiceMessage = None  # type: ignore[misc, assignment]
    MixedMessage = None  # type: ignore[misc, assignment]
    _WeComDefaultLogger = None  # type: ignore[misc, assignment]

try:
    from pi_agent_core import ImageContent as PiImageContent
except ImportError:
    PiImageContent = None  # type: ignore[misc, assignment]

logger = logging.getLogger(__name__)


class _WeComSdkLogger:
    """Forwards wecom-aibot SDK logs; drops DEBUG (heartbeats) unless WECOM_SDK_DEBUG=1."""

    def __init__(self) -> None:
        self._inner = _WeComDefaultLogger()

    def debug(self, message: str, *args: object) -> None:
        if os.environ.get("WECOM_SDK_DEBUG", "").strip().lower() in ("1", "true", "yes"):
            self._inner.debug(message, *args)

    def info(self, message: str, *args: object) -> None:
        self._inner.info(message, *args)

    def warn(self, message: str, *args: object) -> None:
        self._inner.warn(message, *args)

    def error(self, message: str, *args: object) -> None:
        self._inner.error(message, *args)


def wecom_client_from_env() -> WSClient:
    if WSClient is None or WSClientOptions is None or _WeComDefaultLogger is None:
        raise RuntimeError(
            "wecom-aibot is not installed. Install with: uv sync --extra wecom --extra dev "
            "or pip install -e '.[wecom]'"
        )
    bot_id = os.environ.get("WECOM_BOT_ID", "")
    secret = os.environ.get("WECOM_BOT_SECRET", "")
    if not bot_id or not secret:
        raise RuntimeError("WECOM_BOT_ID and WECOM_BOT_SECRET must be set")
    options = WSClientOptions(bot_id=bot_id, secret=secret, logger=_WeComSdkLogger())
    return WSClient(options)


def _session_info(body, cfg: AgentConfig) -> tuple[str, str, str | None]:
    """Extract (userid, session_key, group_id) from a message body."""
    userid = body.from_.userid
    if body.chattype == "group":
        group_id = body.chatid
        session_key = f"wecom:group:{group_id}"
    else:
        group_id = None
        session_key = f"wecom:private:{userid}"
    return userid, session_key, group_id


def _strip_mention(text: str, cfg: AgentConfig) -> str:
    if cfg.wecom_mention:
        return _re.sub(r"^@" + _re.escape(cfg.wecom_mention) + r"\s*", "", text).strip()
    return _re.sub(r"^@\S+\s*", "", text).strip()


def _detect_media_type(data: bytes, url: str) -> str:
    """Detect image MIME type from magic bytes, falling back to URL extension."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    ext = url.rsplit(".", 1)[-1].lower().split("?")[0] if "." in url else ""
    return {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "gif": "image/gif",
        "webp": "image/webp",
    }.get(ext, "image/jpeg")


async def run_wecom_loop(
    *,
    cfg: AgentConfig,
    project_root: Path,
    history: JsonlHistory,
    sessions: AgentSessionManager,
    cli_provider: str | None,
    cli_model: str | None,
) -> None:
    monitor = get_monitor()
    monitor.start()
    _session_locks: dict[str, asyncio.Lock] = {}

    while True:
        client = wecom_client_from_env()

        async def _dispatch(
            frame,
            *,
            userid: str,
            session_key: str,
            group_id: str | None,
            user_text: str,
            user_images=None,
        ):
            stream_id = f"s-{uuid.uuid4().hex[:12]}"
            logger.info("[WeCom RECV] userid=%s session=%s text=%r", userid, session_key, user_text)
            if session_key not in _session_locks:
                _session_locks[session_key] = asyncio.Lock()

            # Open the stream immediately so WeCom shows a thinking indicator while
            # the LLM processes. jasmine-v2 does the same — a space sent right away
            # keeps the stream alive and visible during the generation gap.
            try:
                await client.reply_stream(frame, stream_id, " ", finish=False)
            except Exception:
                logger.exception("[WeCom] Failed to open stream for %s", session_key)

            async with _session_locks[session_key]:
                full = await run_turn(
                    cfg=cfg,
                    project_root=project_root,
                    history_store=history,
                    sessions=sessions,
                    session_key=session_key,
                    channel="wecom",
                    wecom_userid=userid,
                    group_id=group_id,
                    user_text=user_text,
                    user_images=user_images,
                    cli_provider=cli_provider,
                    cli_model=cli_model,
                    on_delta=None,
                )
            # Deliver the complete reply. If we opened a stream, close it with the
            # full text; otherwise fall back to a fresh stream (stream expired).
            await client.reply_stream(frame, stream_id, full, finish=True)
            logger.info("[WeCom SEND] session=%s reply=%r", session_key, full)

        @client.on("message.text")
        async def on_text(frame):  # type: ignore[no-untyped-def]
            if TextMessage is None or not isinstance(frame.body, TextMessage):
                return
            body = frame.body
            userid, session_key, group_id = _session_info(body, cfg)
            text = body.text.content
            if body.chattype == "group":
                text = _strip_mention(text, cfg)
            await _dispatch(
                frame, userid=userid, session_key=session_key, group_id=group_id, user_text=text
            )

        @client.on("message.image")
        async def on_image(frame):  # type: ignore[no-untyped-def]
            if ImageMessage is None or PiImageContent is None:
                return
            if not isinstance(frame.body, ImageMessage):
                return
            body = frame.body
            userid, session_key, group_id = _session_info(body, cfg)
            img = body.image
            try:
                aeskey = img.aeskey
                if aeskey:
                    aeskey += "=" * (-len(aeskey) % 4)
                data, _ = await client.api.download_file(img.url, aeskey)
                media_type = _detect_media_type(data, img.url)
                pi_image = PiImageContent(
                    media_type=media_type, data=base64.b64encode(data).decode()
                )
                logger.info(
                    "[WeCom RECV] image userid=%s session=%s size=%d",
                    userid,
                    session_key,
                    len(data),
                )
                await _dispatch(
                    frame,
                    userid=userid,
                    session_key=session_key,
                    group_id=group_id,
                    user_text="[Image]",
                    user_images=[pi_image],
                )
            except Exception:
                logger.exception("[WeCom] Failed to download image from %s", img.url)
                await _dispatch(
                    frame,
                    userid=userid,
                    session_key=session_key,
                    group_id=group_id,
                    user_text="[Image — failed to load]",
                )

        @client.on("message.file")
        async def on_file(frame):  # type: ignore[no-untyped-def]
            if FileMessage is None or not isinstance(frame.body, FileMessage):
                return
            body = frame.body
            userid, session_key, group_id = _session_info(body, cfg)
            f = body.file
            try:
                aeskey = f.aeskey
                if aeskey:
                    aeskey += "=" * (-len(aeskey) % 4)
                data, filename = await client.api.download_file(f.url, aeskey)
                size_kb = len(data) // 1024
                label = filename or f.url.rsplit("/", 1)[-1].split("?")[0] or "file"
                user_text = f"[File: {label} ({size_kb} KB)]"
                logger.info(
                    "[WeCom RECV] file userid=%s session=%s file=%s size=%dKB",
                    userid,
                    session_key,
                    label,
                    size_kb,
                )
            except Exception:
                logger.exception("[WeCom] Failed to download file from %s", f.url)
                user_text = "[File — failed to load]"
            await _dispatch(
                frame,
                userid=userid,
                session_key=session_key,
                group_id=group_id,
                user_text=user_text,
            )

        @client.on("message.voice")
        async def on_voice(frame):  # type: ignore[no-untyped-def]
            if VoiceMessage is None or not isinstance(frame.body, VoiceMessage):
                return
            body = frame.body
            userid, session_key, group_id = _session_info(body, cfg)
            logger.info("[WeCom RECV] voice userid=%s session=%s", userid, session_key)
            await _dispatch(
                frame,
                userid=userid,
                session_key=session_key,
                group_id=group_id,
                user_text="[Voice message — transcription not available]",
            )

        @client.on("message.mixed")
        async def on_mixed(frame):  # type: ignore[no-untyped-def]
            if MixedMessage is None or PiImageContent is None:
                return
            if not isinstance(frame.body, MixedMessage):
                return
            body = frame.body
            userid, session_key, group_id = _session_info(body, cfg)
            text_parts: list[str] = []
            images: list = []
            for item in body.mixed.msg_item:
                if item.msgtype == "text" and item.text:
                    t = item.text.content
                    if body.chattype == "group":
                        t = _strip_mention(t, cfg)
                    text_parts.append(t)
                elif item.msgtype == "image" and item.image:
                    try:
                        _aeskey = item.image.aeskey
                        if _aeskey:
                            _aeskey += "=" * (-len(_aeskey) % 4)
                        data, _ = await client.api.download_file(item.image.url, _aeskey)
                        media_type = _detect_media_type(data, item.image.url)
                        images.append(
                            PiImageContent(
                                media_type=media_type,
                                data=base64.b64encode(data).decode(),
                            )
                        )
                    except Exception:
                        logger.exception("[WeCom] Failed to download mixed image")
                        text_parts.append("[Image — failed to load]")
            user_text = " ".join(text_parts) if text_parts else ("[Image]" if images else "")
            logger.info(
                "[WeCom RECV] mixed userid=%s session=%s text=%r images=%d",
                userid,
                session_key,
                user_text,
                len(images),
            )
            await _dispatch(
                frame,
                userid=userid,
                session_key=session_key,
                group_id=group_id,
                user_text=user_text,
                user_images=images or None,
            )

        try:
            client.connect()
            while True:
                await asyncio.sleep(3600)
        except Exception as e:
            logger.warning("[WeCom] Connection lost: %s — waiting for network...", e)
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass

        await monitor.wait_for_up()
        await asyncio.sleep(2)
        logger.info("[WeCom] Reconnecting...")
