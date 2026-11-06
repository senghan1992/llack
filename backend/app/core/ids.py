"""Prefixed, ULID-style identifiers (``usr_01J...``)."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

USER_PREFIX = "usr_"
WORKSPACE_PREFIX = "wsp_"
CHANNEL_PREFIX = "chl_"
MESSAGE_PREFIX = "msg_"
FILE_PREFIX = "fil_"
MEMBER_PREFIX = "mem_"
CHANNEL_MEMBER_PREFIX = "cm_"
REACTION_PREFIX = "rx_"
READ_STATE_PREFIX = "rs_"
INVITE_PREFIX = "inv_"
EVENT_PREFIX = "evt_"
ATTENDEE_PREFIX = "att_"
PROJECT_PREFIX = "prj_"
ROADMAP_PREFIX = "rm_"
PROJECT_MEMBER_PREFIX = "pm_"
TASK_PREFIX = "tsk_"
TASK_COMMENT_PREFIX = "tc_"
MILESTONE_PREFIX = "mst_"
ORG_UNIT_PREFIX = "org_"
ORG_MEMBER_PREFIX = "om_"
ORG_MANAGER_PREFIX = "ogm_"


def _encode(value: int, length: int) -> str:
    chars: list[str] = []
    for _ in range(length):
        chars.append(_ALPHABET[value & 0x1F])
        value >>= 5
    return "".join(reversed(chars))


def ulid(now: datetime | None = None) -> str:
    """Return a lexicographically sortable 26 character ULID."""
    moment = now or datetime.now(UTC)
    timestamp = int(moment.timestamp() * 1000)
    return _encode(timestamp, 10) + _encode(secrets.randbits(80), 16)


def new_id(prefix: str) -> str:
    """Return a new prefixed identifier, e.g. ``new_id("usr_")``."""
    return f"{prefix}{ulid()}"
