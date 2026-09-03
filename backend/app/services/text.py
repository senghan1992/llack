"""Message text processing: mentions, slug generation, search snippets.

The message body is Markdown. Mentions use the explicit form `<@USER_ID>` so
renaming a user never breaks an existing message, and the client renders the
display name at read time. The composer converts `@handle` typed by the user
into that form before sending; this module resolves whatever arrives.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping

# <@01J...>  — canonical mention
MENTION_RE = re.compile(r"<@([0-9A-HJKMNP-TV-Z]{26})>")
# @handle  — tolerated on input and normalised server-side
HANDLE_MENTION_RE = re.compile(r"(?<![\w<])@([a-z0-9][a-z0-9._-]{1,63})\b", re.IGNORECASE)
# @김앨리스  — a display name typed the way the UI shows it. Korean teams write
# `@이름`, not `@handle`, and the UI renders every mention as `@표시이름`, so
# people naturally type what they see. The token runs to whitespace or
# punctuation; `resolve_name_mentions` then finds the longest display name it
# starts with, so `@김앨리스님` still reaches 김앨리스.
NAME_MENTION_RE = re.compile(r"(?<![\w<@])@([^\s@<>`*_~,.!?;:()\[\]{}\"'…/\\]{1,64})")
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


def extract_broadcast(body: str) -> str | None:
    """"channel" for @channel/@everyone, "here" for @here alone, else None.

    `@channel` outranks `@here` when both appear: the wider call wins.
    """
    scannable = strip_code(body)
    words = {m.lower() for m in EVERYONE_RE.findall(scannable)}
    if not words:
        return None
    if words & {"channel", "everyone"}:
        return "channel"
    return "here"


def extract_handle_mentions(body: str) -> list[str]:
    """Handles written as plain `@name`, for the server to resolve to ids."""
    scannable = strip_code(body)
    found = HANDLE_MENTION_RE.findall(scannable)
    reserved = {"here", "channel", "everyone"}
    return list(dict.fromkeys(h.lower() for h in found if h.lower() not in reserved))


def extract_name_mention_tokens(body: str) -> list[str]:
    """Candidate `@something` tokens that are not ASCII handles.

    Returned lower-cased and de-duplicated; the caller matches them against
    display names. ASCII-only tokens are left to the handle path — a handle
    and a display name can legitimately differ, and the handle wins.
    """
    scannable = strip_code(body)
    tokens: list[str] = []
    for match in NAME_MENTION_RE.finditer(scannable):
        token = match.group(1)
        if token.isascii():
            continue
        tokens.append(token.lower())
    return list(dict.fromkeys(tokens))


def name_prefixes(tokens: list[str], *, max_length: int = 32) -> list[str]:
    """Every prefix of every token, for one IN-list lookup of display names."""
    prefixes: set[str] = set()
    for token in tokens:
        for end in range(1, min(len(token), max_length) + 1):
            prefixes.add(token[:end])
    return sorted(prefixes)


def rewrite_names_to_mentions(body: str, name_to_id: dict[str, str]) -> str:
    """Turn `@표시이름` into `<@id>`, longest matching name first.

    `name_to_id` keys are lower-cased display names. A token such as
    `@김앨리스님` matches `김앨리스` and keeps the trailing `님` as text.
    """
    if not name_to_id:
        return body

    protected: list[str] = []

    def _protect(match: re.Match[str]) -> str:
        protected.append(match.group(0))
        return f"\x00{len(protected) - 1}\x00"

    stashed = CODE_BLOCK_RE.sub(_protect, body)
    names = sorted(name_to_id, key=len, reverse=True)

    def _replace(match: re.Match[str]) -> str:
        token = match.group(1)
        if token.isascii():
            return match.group(0)
        lowered = token.lower()
        for name in names:
            if lowered.startswith(name):
                rest = token[len(name) :]
                return f"<@{name_to_id[name]}>{rest}"
        return match.group(0)

    rewritten = NAME_MENTION_RE.sub(_replace, stashed)
    return re.sub(r"\x00(\d+)\x00", lambda m: protected[int(m.group(1))], rewritten)


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


def plain_text_preview(
    body: str, *, limit: int = 120, names: Mapping[str, str] | None = None
) -> str:
    """Strip Markdown down to something usable in a sidebar or notification.

    `names` maps user ids to display names so a mention reads as `@김앨리스`.
    Mentions are resolved *before* the Markdown strip below: the canonical form
    is `<@ID>`, and that strip removes `>`, which used to leave a half-eaten
    `<@01J…` in every notification that mentioned somebody.
    """
    text = CODE_BLOCK_RE.sub("[코드]", body)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "[이미지]", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)

    def _mention(match: re.Match[str]) -> str:
        display = (names or {}).get(match.group(1))
        return f"@{display}" if display else "@사용자"

    text = MENTION_RE.sub(_mention, text)
    # Strip Markdown *markers*, not characters: `landing_cta_click` and
    # `9/13~9/15` used to come out as `landingctaclick` and `9/139/15`.
    text = re.sub(r"\*\*|__|~~|\*", "", text)
    text = re.sub(r"(?<!\w)_([^_\n]+)_(?!\w)", r"\1", text)
    text = re.sub(r"^[ \t]{0,3}#{1,6}[ \t]+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[ \t]*>[ \t]?", "", text, flags=re.MULTILINE)
    table_rule = r"^[ \t]*\|?[ \t]*:?-{3,}:?[ \t]*(\|[ \t]*:?-{3,}:?[ \t]*)*\|?[ \t]*$"
    text = re.sub(table_rule, "", text, flags=re.MULTILINE)
    text = text.replace("|", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit] + ("…" if len(text) > limit else "")
