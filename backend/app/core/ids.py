"""Sortable, URL-safe identifiers (ULID) plus prefixed public IDs.

Every row gets a ULID: 48-bit millisecond timestamp + 80 bits of randomness,
Crockford base32-encoded to 26 chars. Two properties we care about:

* Lexicographic order == creation order, so `ORDER BY id` on messages is a
  b-tree index scan with no separate timestamp column needed.
* Generated client- or server-side without coordination, so the desktop app
  can assign an ID to an optimistic message and the server keeps it.
"""

from __future__ import annotations

import os
import threading
import time

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_DECODE = {c: i for i, c in enumerate(_CROCKFORD)}
# Crockford treats these as their digit look-alikes.
_DECODE.update({"O": 0, "I": 1, "L": 1})

ULID_LENGTH = 26


def _encode(value: int, length: int) -> str:
    out = bytearray(length)
    for i in range(length - 1, -1, -1):
        out[i] = ord(_CROCKFORD[value & 0x1F])
        value >>= 5
    return out.decode("ascii")


_MAX_RANDOM = (1 << 80) - 1
_lock = threading.Lock()
_last_ms = -1
_last_random = 0


def new_ulid(timestamp_ms: int | None = None) -> str:
    """Return a fresh 26-char ULID, monotonic within a process.

    Plain random ULIDs generated in the same millisecond do not sort in
    creation order. Message ordering depends on `ORDER BY id`, so within a
    millisecond we increment the previous randomness instead of drawing new
    bytes — the monotonic variant from the ULID spec.
    """
    global _last_ms, _last_random

    if timestamp_ms is not None:
        # Explicit timestamp (backfills, tests): no monotonic bookkeeping.
        return _encode(timestamp_ms, 10) + _encode(
            int.from_bytes(os.urandom(10), "big"), 16
        )

    with _lock:
        now_ms = int(time.time() * 1000)
        if now_ms > _last_ms:
            _last_ms = now_ms
            # Leave headroom so a busy millisecond cannot overflow into the
            # next timestamp.
            _last_random = int.from_bytes(os.urandom(10), "big") >> 1
        else:
            # Clock went backwards or we are still in the same millisecond.
            _last_random += 1
            if _last_random > _MAX_RANDOM:
                _last_ms += 1
                _last_random = int.from_bytes(os.urandom(10), "big") >> 1
        ts, randomness = _last_ms, _last_random

    return _encode(ts, 10) + _encode(randomness, 16)


def ulid_timestamp_ms(value: str) -> int:
    """Extract the embedded millisecond timestamp from a ULID."""
    if len(value) != ULID_LENGTH:
        raise ValueError(f"not a ULID: {value!r}")
    ts = 0
    for ch in value[:10].upper():
        try:
            ts = (ts << 5) | _DECODE[ch]
        except KeyError as exc:
            raise ValueError(f"invalid ULID character {ch!r}") from exc
    return ts


def is_ulid(value: str) -> bool:
    if len(value) != ULID_LENGTH:
        return False
    return all(ch in _DECODE for ch in value.upper())


def new_token(nbytes: int = 32) -> str:
    """Opaque high-entropy secret (refresh tokens, app tokens, invite codes)."""
    import secrets

    return secrets.token_urlsafe(nbytes)
