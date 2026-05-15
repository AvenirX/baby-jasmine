from __future__ import annotations

import re

from emoji import analyze
from emoji.tokenizer import EmojiMatch

from baby_jasmine.config_models import ReplyPolicy

_CJK_RE = re.compile(r"[一-鿿㐀-䶿]")
_LATIN_WORD_RE = re.compile(r"[a-zA-Z]{4,}")
_RELAY_RE = re.compile(r"\[[^\]]*\]")


def count_emoji_units(text: str) -> int:
    n = 0
    for tok in analyze(text, non_emoji=True):
        if isinstance(tok.value, EmojiMatch):
            n += 1
    return n


def has_text_content(text: str) -> bool:
    stripped = _RELAY_RE.sub("", text)
    return bool(_CJK_RE.search(stripped) or _LATIN_WORD_RE.search(stripped))


def cap_emojis(text: str, max_emojis: int) -> str:
    if max_emojis <= 0:
        max_emojis = 0
    parts: list[str] = []
    kept = 0
    for tok in analyze(text, non_emoji=True):
        if isinstance(tok.value, EmojiMatch):
            if kept < max_emojis:
                parts.append(tok.chars)
                kept += 1
        else:
            parts.append(tok.chars)
    return "".join(parts)


def should_run_repair(draft: str, policy: ReplyPolicy) -> bool:
    if not policy.repair_enabled:
        return False
    if policy.emoji_only:
        return has_text_content(draft)
    return count_emoji_units(draft) > policy.max_emojis


def repair_user_message(*, user_text: str, draft: str, max_emojis: int) -> str:
    return (
        f"User message:\n{user_text}\n\n"
        f"Draft reply:\n{draft}\n\n"
        "Rewrite the draft as the final reply only. Keep the same language, Baby Jasmine's "
        f"voice, and at most {max_emojis} emoji in the entire message. "
        "Preserve any text inside [...] relay brackets exactly as-is. "
        "Output only the reply text, no explanations or labels."
    )


def emoji_only_repair_message(*, user_text: str, draft: str) -> str:
    return (
        f"User message:\n{user_text}\n\n"
        f"Draft reply:\n{draft}\n\n"
        "Rewrite as Baby Jasmine using ONLY emoji and kaomoji (颜文字). "
        "No text, no Chinese characters, no English words. "
        "Kaomoji ASCII/katakana is fine: (づ｡◕‿‿◕｡)づ ヽ(・∀・)ノ (╥_╥)\n"
        "Preserve any text inside [...] relay brackets exactly as-is. "
        "Output only the reply, nothing else."
    )


REPAIR_SYSTEM_PROMPT = (
    "You shorten or rewrite assistant replies to obey a strict emoji budget. "
    "Output only the final message body, nothing else."
)

EMOJI_ONLY_REPAIR_SYSTEM = (
    "You rewrite assistant replies to use ONLY emoji and kaomoji (颜文字 like ヽ(•‿•)ノ). "
    "No words. No Chinese. No English. Only emoji 🎉 and kaomoji. "
    "Preserve any [...] relay brackets and their content verbatim. "
    "Output only the final reply, nothing else."
)
