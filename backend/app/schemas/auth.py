"""Authentication payloads."""

from __future__ import annotations

from datetime import datetime

from pydantic import EmailStr, Field

from app.schemas.common import Handle, Payload, Schema
from app.schemas.user import UserOut


class DeviceInfo(Payload):
    device_name: str | None = Field(default=None, max_length=160)
    platform: str | None = Field(default=None, max_length=32)
    app_version: str | None = Field(default=None, max_length=32)


class RegisterRequest(Payload):
    email: EmailStr
    password: str = Field(min_length=10, max_length=256)
    display_name: str = Field(min_length=1, max_length=120)
    handle: Handle | None = None
    device: DeviceInfo | None = None
    # Consumed at sign-up: the account is created and joins the inviting
    # workspace in one step. Mandatory when the server runs invite-gated
    # (LLACK_REQUIRE_INVITE).
    invite_token: str | None = Field(default=None, min_length=10, max_length=512)


class LoginRequest(Payload):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)
    device: DeviceInfo | None = None


class RefreshRequest(Payload):
    refresh_token: str = Field(min_length=10, max_length=512)


class TokenPair(Schema):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_at: datetime
    expires_in: int


class AuthResponse(Schema):
    user: UserOut
    tokens: TokenPair


class SessionOut(Schema):
    id: str
    device_name: str | None
    platform: str | None
    app_version: str | None
    ip_address: str | None
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime
    is_current: bool = False


class ChangePasswordRequest(Payload):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=10, max_length=256)


class ForgotPasswordRequest(Payload):
    email: EmailStr


class ResetPasswordRequest(Payload):
    email: EmailStr
    code: str = Field(min_length=4, max_length=12)
    new_password: str = Field(min_length=10, max_length=256)
