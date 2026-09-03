"""방해 금지: is this person to be left alone right now?

Two mechanisms, one answer. A one-off pause (`notify_paused_until`) wins over
everything; otherwise the daily window `dnd_start`–`dnd_end` applies on the
configured weekdays, evaluated in the *user's* timezone — a 22:00–08:00 window
crosses midnight and belongs to the day it started on. Counters keep counting
either way: DND silences toasts, not the truth.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

HHMM_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
DEFAULT_DAYS = [0, 1, 2, 3, 4]


def parse_hhmm(value: str) -> time:
    match = HHMM_RE.match(value)
    if not match:
        raise ValueError("time must be HH:MM (24h)")
    return time(int(match.group(1)), int(match.group(2)))


def in_dnd(
    *,
    dnd_start: str | None,
    dnd_end: str | None,
    dnd_days: list[int] | None,
    paused_until: datetime | None,
    timezone: str,
    now: datetime | None = None,
) -> bool:
    now = now or datetime.now(UTC)
    if paused_until is not None:
        paused = paused_until if paused_until.tzinfo else paused_until.replace(tzinfo=UTC)
        if paused > now:
            return True
    if not dnd_start or not dnd_end:
        return False
    try:
        start = parse_hhmm(dnd_start)
        end = parse_hhmm(dnd_end)
    except ValueError:
        return False
    try:
        local = now.astimezone(ZoneInfo(timezone or "UTC"))
    except (ZoneInfoNotFoundError, ValueError):
        local = now.astimezone(UTC)
    days = set(dnd_days if dnd_days is not None else DEFAULT_DAYS)
    current = local.time().replace(second=0, microsecond=0)
    weekday = local.weekday()

    if start <= end:
        # Same-day window, e.g. 12:00–13:00.
        return weekday in days and start <= current < end
    # Crosses midnight, e.g. 22:00–08:00: the evening half belongs to today's
    # weekday, the morning half to the day the window started on (yesterday).
    if current >= start:
        return weekday in days
    if current < end:
        return ((weekday - 1) % 7) in days
    return False
