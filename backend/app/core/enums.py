"""Enumerations shared by models, schemas and the realtime protocol.

These are plain `str` enums stored as strings in the database. Adding a member
is a backwards-compatible change; removing one is not.
"""

from __future__ import annotations

from enum import StrEnum


class WorkspaceRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    GUEST = "guest"

    @property
    def rank(self) -> int:
        return {"guest": 0, "member": 1, "admin": 2, "owner": 3}[self.value]

    def at_least(self, other: WorkspaceRole) -> bool:
        return self.rank >= other.rank


class ChannelKind(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"
    DM = "dm"
    GROUP_DM = "group_dm"

    @property
    def is_conversation(self) -> bool:
        """DMs have no name/topic and cannot be joined or archived."""
        return self in (ChannelKind.DM, ChannelKind.GROUP_DM)


class ChannelRole(StrEnum):
    ADMIN = "admin"
    MEMBER = "member"


class NotificationLevel(StrEnum):
    ALL = "all"
    MENTIONS = "mentions"
    NOTHING = "nothing"


class MessageKind(StrEnum):
    USER = "user"
    SYSTEM = "system"   # "X joined the channel"
    APP = "app"         # posted by an installed mini-app / bot


class AppKind(StrEnum):
    PANEL = "panel"     # renders UI in the app panel
    BOT = "bot"         # posts messages, no UI
    BOTH = "both"
    # An external site embedded as-is in the main pane. No bridge, no token,
    # no scopes — the host lends it a frame and nothing else.
    LINK = "link"


class AppStatus(StrEnum):
    DRAFT = "draft"                    # visible and installable only in its owner workspace
    PENDING_REVIEW = "pending_review"  # submitted for company-wide publication
    PUBLISHED = "published"            # in every workspace's directory
    REJECTED = "rejected"              # reviewer said no; still usable at home, resubmittable
    DISABLED = "disabled"


class AppScope(StrEnum):
    """Capabilities a mini-app may request in its manifest.

    The host grants these at install time; every bridge call and REST call made
    with an app token is checked against the installation's granted scopes.
    """

    IDENTITY_READ = "identity:read"
    CHANNELS_READ = "channels:read"
    MESSAGES_READ = "messages:read"
    MESSAGES_WRITE = "messages:write"
    FILES_READ = "files:read"
    FILES_WRITE = "files:write"
    USERS_READ = "users:read"
    NOTIFY = "notify"
    STORAGE = "storage"        # per-installation key/value store
    PANEL_UI = "panel:ui"      # open dialogs, set panel badge/title


class PresenceState(StrEnum):
    ACTIVE = "active"
    AWAY = "away"
    DND = "dnd"
    OFFLINE = "offline"
