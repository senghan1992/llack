# Models

## Overview

Transport-agnostic data layer for the Llack API. Every class in this package is a
plain immutable Dart object with a `fromJson` factory that maps the snake_case
wire format onto Dart camelCase fields, plus hand-written enums that carry both
the wire value and the Korean display label used across the UI.

This package has no dependencies on Flutter widgets, on `ApiService`, or on
`AppState`. It only needs `dart:core` and `dart:convert`, so both the REST path
(`mobile/lib/services/api_service.dart`) and the WebSocket path
(`mobile/lib/providers/app_state_realtime.dart`) can decode the same payloads.
Workspace invitations are represented by `Invite`; project member edits use the
narrow `Project.copyWith` contract.

## Interface

### Enums

- `enum Presence` — `online`, `busy`, `dnd`, `away`, `brb`, `offline`.
  - `static Presence Presence.fromString(String? val)`
  - `String get Presence.apiValue` — the enum constant's `name`.
  - `String get Presence.label` — Korean label (`온라인`, `바쁨`, `방해 금지`, `잠시 자리 비움`, `곧 돌아오겠습니다`, `오프라인`).
- `enum Role` — `owner`, `admin`, `member`.
  - `static Role Role.fromString(String? val)`
  - `String get Role.label` — `소유자`, `관리자`, `멤버`.
- `enum EventResponse` — `accepted`, `declined`, `tentative`, `pending`.
  - `static EventResponse EventResponse.fromString(String? val)`
  - `String get EventResponse.label` — `참석`, `불참`, `미정`, `대기`.
- `enum TaskStatus` — `request`, `todo`, `inProgress`, `done`.
  - `static TaskStatus TaskStatus.fromString(String? val)`
  - `String get TaskStatus.apiValue` — wire strings `request`, `todo`, `in-progress`, `done`.
  - `String get TaskStatus.label` — `요청`, `할 일`, `진행 중`, `완료`.

### Model classes

All classes below expose final fields, a `factory X.fromJson(Map<String, dynamic> json)`,
and — where the UI needs to edit a value locally — a `copyWith` method.

- `User` — `id`, `email`, `name`, `title?`, `avatarColor?`, `avatarUrl?`, `presence`, `lastSeenAt?`, `createdAt?`; `fromJson`, `toJson`, `copyWith({name, title, avatarColor, presence})`.
- `Member` — `user`, `role`, `joinedAt?`; `fromJson`.
- `Invite` — `id`, `workspaceId`, `email`, `role`, `token`, `createdBy`, `createdAt?`, `expiresAt?`; `fromJson`.
- `Workspace` — `id`, `name`, `slug`, `createdAt?`; `fromJson`.
- `Reaction` — `emoji`, `count`, `userIds`, `me`; `fromJson`.
- `FileRef` — `id`, `name`, `url`, `mime`, `size`; `fromJson`.
- `ReplyTo` — `id`, `authorName`, `body`, `deleted`; `fromJson`.
- `Message` — `id`, `channelId`, `userId`, `author`, `body`, `kind`, `parentId?`, `replyToId?`, `replyTo?`, `inline`, `createdAt`, `editedAt?`, `deletedAt?`, `replyCount`, `lastReplyAt?`, `pinned`, `reactions`, `attachments`; getters `isSystem`, `isDeleted`, `isThreadReply`; `fromJson`, `copyWith`.
- `Channel` — `id`, `workspaceId`, `name`, `topic?`, `purpose?`, `kind`, `isPrivate`, `createdBy`, `createdAt`, `memberCount`, `unreadCount`, `lastMessageAt?`, `dmUser?`, `members?`, `isMember`; getters `isDm`, `displayName`; `fromJson`, `copyWith`.
- `ScheduleAttendee` — `user`, `response`; `fromJson`.
- `ScheduleEvent` — `id`, `workspaceId`, `title`, `description`, `location`, `startsAt`, `endsAt`, `allDay`, `isPrivate`, `createdBy`, `channelId?`, `createdAt`, `updatedAt`, `attendees`, `myResponse?`; `fromJson`.
- `Project` — `id`, `workspaceId`, `name`, `description`, `purpose`, `deliverables`, `channelId?`, `createdBy`, `isArchived`, `createdAt`, `updatedAt`, `members`, `isMember`, `openTasks`, `totalTasks`, `doneTasks`; `fromJson`, `copyWith({String? name, String? description, String? channelId, bool? isArchived, List<User>? members})`.
- `TaskComment` — `id`, `taskId`, `userId`, `author`, `body`, `createdAt`; `fromJson`.
- `Task` — `id`, `projectId`, `title`, `description`, `status`, `roadmapId?`, `roadmapName?`, `milestoneId?`, `milestoneName?`, `milestoneColor?`, `assigneeId?`, `assignee?`, `createdBy`, `startAt?`, `dueAt?`, `position`, `createdAt`, `updatedAt`, `comments`, `commentCount`; `fromJson`, `copyWith`.
- `Roadmap` — `id`, `projectId`, `name`, `position`, `taskCount`; `fromJson`.
- `Milestone` — `id`, `projectId`, `title`, `startAt`, `endAt`, `color`, `progress`, `description`, `taskCount`, `doneCount`; `fromJson`.
- `OrgUnit` — `id`, `workspaceId`, `parentId?`, `name`, `kind`, `description`, `depth`, `memberCount`, `childCount`, `members`, `managers`; `fromJson`.
- `OrgOverview` — `units`, `admins`, `myRole`; `fromJson`.
- `SearchResult` — `message`, `channel`; `fromJson`.
- `Bootstrap` — `workspace`, `channels`, `dms`, `members`, `me`; `fromJson`.
- `Session` — `accessToken`, `refreshToken`, `user`, `workspace`; `fromJson`.

## Invariants

- `[mobile/lib/models/models.dart:Presence.fromString]` `Presence.fromString` returns `Presence.offline` for `null` or any unrecognized string.
- `[mobile/lib/models/models.dart:Role.fromString]` `Role.fromString` returns `Role.member` for `null` or any value other than `'owner'`/`'admin'`.
- `[mobile/lib/models/models.dart:EventResponse.fromString]` `EventResponse.fromString` returns `EventResponse.pending` for `null` or any unrecognized string.
- `[mobile/lib/models/models.dart:TaskStatus.fromString]` `TaskStatus.fromString` maps both `'in-progress'` and `'in_progress'` to `TaskStatus.inProgress` and returns `TaskStatus.todo` for `null` or any unrecognized string.
- `[mobile/lib/models/models.dart:TaskStatus.apiValue]` `TaskStatus.apiValue` emits `'in-progress'` for `TaskStatus.inProgress`, which `TaskStatus.fromString` parses back to the same constant.
- `[mobile/lib/models/models.dart:User.fromJson]` `User.fromJson` coerces a missing or non-string `id`, `email`, and `name` to the empty string via `?? ''`.
- `[mobile/lib/models/models.dart:User.fromJson]` `User.fromJson` maps the snake_case keys `avatar_color` and `avatar_url` onto `avatarColor` and `avatarUrl`, and parses `last_seen_at` / `created_at` with `DateTime.tryParse` only when the key is non-null, so an unparsable value yields `null` rather than an exception.
- `[mobile/lib/models/models.dart:User.toJson]` `User.toJson` emits exactly the keys `id`, `email`, `name`, `title`, `avatar_color`, `avatar_url`, and `presence` (serialized as `presence.apiValue`); it omits `lastSeenAt` and `createdAt`.
- `[mobile/lib/models/models.dart:User.copyWith]` `User.copyWith` can only replace `name`, `title`, `avatarColor`, and `presence`; `id`, `email`, `avatarUrl`, `lastSeenAt`, and `createdAt` are carried over unchanged.
- `[mobile/lib/models/models.dart:Member.fromJson]` `Member.fromJson` reads the nested user from `json['user']` and falls back to interpreting the same map itself as the user when the `user` key is absent.
- `[mobile/lib/models/models.dart:Invite.fromJson]` `Invite.fromJson` maps `workspace_id` and `created_by` from the snake_case wire format, defaults `role` to `'member'`, and defaults missing string values to the empty string. `created_at` and `expires_at` stay `null` when absent. A non-null timestamp is cast to `String` before parsing, so a non-string value raises a cast error while an unparsable string becomes `null`.
- `[mobile/lib/models/models.dart:Project.copyWith]` `Project.copyWith` can only replace `name`, `description`, `channelId`, `isArchived`, and `members`. A `null` argument preserves the current value, so this method cannot clear `channelId`; project identity, purpose/deliverables, ownership, timestamps, membership flag, and task counters are carried over unchanged.
- `[mobile/lib/models/models.dart:Reaction.fromJson]` `Reaction.fromJson` converts every `user_ids` element with `toString()`, defaults the list to empty when the key is missing or null, defaults `me` to `false`, and `count` to `0`.
- `[mobile/lib/models/models.dart:Message.fromJson]` `Message.fromJson` defaults `kind` to `'text'`, `inline` to `false`, `replyCount` to `0`, `pinned` to `false`, and `reactions`/`attachments` to empty lists; `created_at` falls back to `DateTime.now()` when missing or unparsable while `edited_at`, `deleted_at`, and `last_reply_at` become `null` when absent.
- `[mobile/lib/models/models.dart:Message.fromJson]` `Message.fromJson` casts each element of `reactions` and `attachments` to `Map<String, dynamic>`, so a non-map element raises a cast error.
- `[mobile/lib/models/models.dart:Channel.fromJson]` `Channel.fromJson` defaults `kind` to `'channel'`, `is_private` to `false`, `is_member` to `true`, `member_count`/`unread_count` to `0`, and `created_at` to `DateTime.now()` when unparsable; `members` stays `null` when the key is absent, unlike the other list fields which default to empty lists.
- `[mobile/lib/models/models.dart:Channel.copyWith]` `Channel.copyWith` can only replace `unreadCount`, `lastMessageAt`, `topic`, `name`, and `dmUser`.
- `[mobile/lib/models/models.dart:ScheduleEvent.fromJson]` `ScheduleEvent.fromJson` falls back to `DateTime.now()` for `starts_at`, `ends_at`, `created_at`, and `updated_at` when the values are missing or unparsable, and leaves `myResponse` as `null` when `my_response` is absent.
- `[mobile/lib/models/models.dart:Project.fromJson]` `Project.fromJson` defaults `is_member` to `false`, unlike `Channel.fromJson` which defaults `is_member` to `true`.
- `[mobile/lib/models/models.dart:Task.fromJson]` `Task.fromJson` derives `status` through `TaskStatus.fromString`, so an unknown status string becomes `TaskStatus.todo`.
- `[mobile/lib/models/models.dart:Task.copyWith]` `Task.copyWith` can only replace `title`, `description`, `status`, `assignee`, `assigneeId`, `dueAt`, `comments`, and `commentCount`; roadmap/milestone metadata, `position`, and timestamps are carried over unchanged.
- `[mobile/lib/models/models.dart:Milestone.fromJson]` `Milestone.fromJson` defaults `color` to `'#1C785C'`, `description` to `''`, the counters to `0`, and coerces `progress` with `(json['progress'] as num?)?.toDouble() ?? 0.0`.
- `[mobile/lib/models/models.dart:OrgOverview.fromJson]` `OrgOverview.fromJson` derives `myRole` through `Role.fromString`, so an unknown role string becomes `Role.member`.
- `[mobile/lib/models/models.dart:Bootstrap.fromJson]` `Bootstrap.fromJson` casts `workspace` and `me` to non-nullable `Map<String, dynamic>`, so a missing key raises a cast error, while the `channels`, `dms`, and `members` lists default to empty lists.
- `[mobile/lib/models/models.dart:Session.fromJson]` `Session.fromJson` coerces missing `access_token` and `refresh_token` to the empty string.
- `[mobile/lib/models/models.dart:User]` None of the model classes override `==` or `hashCode`, so two instances with identical field values are not equal by `==`.
- `[mobile/lib/models/models.dart:Message]` Every model field is declared `final`, but list-typed fields hold ordinary growable lists created by `.toList()` in the `fromJson` factories rather than unmodifiable lists, except where the constructor default is the `const []` literal.

## Side Effects

- None. The models package performs no I/O, no network calls, no disk access, and no global state mutation. All decoding is pure.

## Verification

- Run: `flutter test` (from the `mobile/` directory)
