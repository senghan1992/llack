"""Short-lived, file-scoped download tokens for media elements.

`<video src>` and `<img src>` cannot carry an Authorization header, and the
transcript should not have to pull a 200 MB recording through fetch() into a
blob just to seek in it. So a client that *has* passed the normal read check
asks for a token, and the download route accepts that token in the query
string instead of a bearer.

The token is `base64url(file_id|exp|hmac)`. It names exactly one file, lives
ten minutes, and is signed with the server secret — possession of a token is
the authorisation, which is why minting it requires the same read check the
download itself would run.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

from app.core.config import settings


def _sign(file_id: str, exp: int) -> bytes:
    message = f"{file_id}|{exp}".encode()
    return hmac.new(settings.secret_key.encode(), message, hashlib.sha256).digest()[:20]


def mint(file_id: str, *, ttl_seconds: int | None = None) -> tuple[str, int]:
    """Return (token, expires_at_epoch)."""
    exp = int(time.time()) + (ttl_seconds or settings.media_token_ttl_seconds)
    raw = f"{file_id}|{exp}|".encode() + _sign(file_id, exp)
    return base64.urlsafe_b64encode(raw).decode().rstrip("="), exp


def verify(token: str, file_id: str) -> bool:
    try:
        padded = token + "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(padded.encode())
        head, _, signature = raw.rpartition(b"|")
        token_file_id, _, exp_text = head.decode().partition("|")
        exp = int(exp_text)
    except Exception:  # noqa: BLE001 — any malformed token is simply invalid
        return False
    if token_file_id != file_id or exp < time.time():
        return False
    return hmac.compare_digest(signature, _sign(file_id, exp))
