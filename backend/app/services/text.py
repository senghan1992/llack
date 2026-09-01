"""Message text processing: mentions, slug generation, search snippets.

The message body is Markdown. Mentions use the explicit form `<@USER_ID>` so
renaming a user never breaks an existing message, and the client renders the
display name at read time. The composer converts `@handle` typed by the user
into that form before sending; this module resolves whatever arrives.
"""

from __future__ import annotations

import re
import unicodedata

# <@01J...>  — canonical mention
MENTION_RE = re.compile(r"<@([0-9A-HJKMNP-TV-Z]{26})>")
# @handle  — tolerated on input and normalised server-side
HANDLE_MENTION_RE = re.compile(r"(?<![\w<])@([a-z0-9][a-z0-9._-]{1,63})\b", re.IGNORECASE)
# <#01J...>  — channel link
CHANNEL_RE = re.compile(r"<#([0-9A-HJKMNP-TV-Z]{26})>")
EVERYONE_RE = re.compile(r"(?<![\w<])@(here|channel|everyone)\b", re.IGNORECASE)

# Fenced and inline code must not produce mentions — pasting a code sample
# containing "@channel" should not ping the whole channel.
CODE_BLOCK_RE = re.compile(r"```.*?```|~~~.*?~~~|`[^`\n]+`", re.DOTALL)


def strip_code(text: str) -> str:
    """Blank out code spans, preserving length so offsets stay valid."""
    return CODE_BLOCK_RE.sub(lambda m: " " * len(m.group(0)), text)


def extract_mentions(body: str) -> tuple[list[str], bool]:
    """Return (mentioned user ids, mentions_everyone), ignoring code spans."""
    scannable = strip_code(body)
    user_ids = list(dict.fromkeys(MENTION_RE.findall(scannable)))
    return user_ids, bool(EVERYONE_RE.search(scannable))


def extract_handle_mentions(body: str) -> list[str]:
    """Handles written as plain `@name`, for the server to resolve to ids."""
    scannable = strip_code(body)
    found = HANDLE_MENTION_RE.findall(scannable)
    reserved = {"here", "channel", "everyone"}
    return list(dict.fromkeys(h.lower() for h in found if h.lower() not in reserved))


def extract_channel_links(body: str) -> list[str]:
    return list(dict.fromkeys(CHANNEL_RE.findall(strip_code(body))))


def rewrite_handles_to_mentions(body: str, handle_to_id: dict[str, str]) -> str:
    """Turn `@handle` into `<@id>` for handles that resolved to a real user."""
    if not handle_to_id:
        return body

    protected: list[str] = []

    def _protect(match: re.Match[str]) -> str:
        protected.append(match.group(0))
        return f"\x00{len(protected) - 1}\x00"

    stashed = CODE_BLOCK_RE.sub(_protect, body)

    def _replace(match: re.Match[str]) -> str:
        user_id = handle_to_id.get(match.group(1).lower())
        return f"<@{user_id}>" if user_id else match.group(0)

    rewritten = HANDLE_MENTION_RE.sub(_replace, stashed)
    return re.sub(r"\x00(\d+)\x00", lambda m: protected[int(m.group(1))], rewritten)


def slugify(value: str, *, max_length: int = 80) -> str:
    """Channel-name slug. Keeps Hangul, since '#개발-공지' is a valid name."""
    normalised = unicodedata.normalize("NFKC", value).strip().lower()
    normalised = re.sub(r"[\s_]+", "-", normalised)
    normalised = re.sub(r"[^0-9a-z가-힣ㄱ-ㆎ.\-]", "", normalised)
    normalised = re.sub(r"-{2,}", "-", normalised).strip("-.")
    return normalised[:max_length] or "channel"


def make_snippet(body: str, query: str, *, radius: int = 90) -> str:
    """Search result snippet with the first match wrapped in <mark>."""
    terms = [t for t in re.split(r"\s+", query.strip()) if t]
    if not terms:
        return body[: radius * 2]

    lowered = body.lower()
    position = -1
    matched = ""
    for term in terms:
        found = lowered.find(term.lower())
        if found != -1 and (position == -1 or found < position):
            position, matched = found, term
    if position == -1:
        return body[: radius * 2]

    start = max(0, position - radius)
    end = min(len(body), position + len(matched) + radius)
    snippet = body[start:end]
    highlighted = re.sub(
        f"({re.escape(matched)})", r"<mark>\1</mark>", snippet, count=1, flags=re.IGNORECASE
    )
    return ("…" if start > 0 else "") + highlighted + ("…" if end < len(body) else "")


def plain_text_preview(body: str, *, limit: int = 120) -> str:
    """Strip Markdown down to something usable in a sidebar or notification."""
    text = CODE_BLOCK_RE.sub("[코드]", body)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "[이미지]", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[*_~>#|]+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit] + ("…" if len(text) > limit else "")
