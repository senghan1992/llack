# Widgets

## Overview

Reusable presentation widgets shared across the screen layer. Nothing in this
package talks to the backend directly, except `MessageAttachments`, which
resolves file URLs and reads the access token to authenticate image loads.

The package holds three groups:

- **Feedback** — `showAppSnackBar` / `AppSnackBar` (app-styled snack bars that
  also render above modal routes) and `ConnectionBanner` /
  `ConnectionBannerStrip` (the realtime-disconnect banner).
- **Identity** — `LlackAvatar` and `PresenceBadge`.
- **Message rendering** — `MessageBubble`, `MessageDeletedMarker`,
  `MessageComposer`, `MessageAttachments` and `MessageMarkdown` (the
  markdown body renderer).

Message rendering also reads one device-level setting: the clock format that
`MessageBubble` uses for timestamps comes from
`mobile/lib/services/device_settings.dart`, and the composer's attachment and
emoji affordances are driven by injected callbacks, so the package never
uploads or sends anything on its own.

## Interface

### Feedback

- `void showAppSnackBar(BuildContext context, String message, {Duration duration = const Duration(seconds: 4), String? actionLabel, VoidCallback? onAction})` — top-level function (`mobile/lib/widgets/app_snack_bar.dart`).
- `class AppSnackBar` — public `StatefulWidget` with public final fields `String message`, `Duration duration`, `String? actionLabel`, `VoidCallback? onAction`, `VoidCallback onDismiss`; const constructor `AppSnackBar({super.key, required this.message, required this.duration, this.actionLabel, this.onAction, required this.onDismiss})`.
- `bool isConnectionLost(AppState state)` — top-level function (`mobile/lib/widgets/connection_banner.dart`).
- `PreferredSizeWidget? connectionBannerBottom(AppState state)` — top-level function returning a `ConnectionBannerStrip` when the connection is lost and `null` otherwise.
- `class ConnectionBanner` — public `StatelessWidget`, const constructor `ConnectionBanner({super.key})`; the shell-level banner above the app bar, including the status-bar inset padding.
- `class ConnectionBannerStrip implements PreferredSizeWidget` — public `StatelessWidget` with const constructor `ConnectionBannerStrip({super.key})`, `static const double height = 30`, and `Size get preferredSize => const Size.fromHeight(height)`.

### Identity

- `class LlackAvatar` — public `StatelessWidget` with public final fields `String name`, `String? avatarUrl`, `String? avatarColor`, `Presence? presence`, `double size`, `double fontSize`; const constructor `LlackAvatar({super.key, required this.name, this.avatarUrl, this.avatarColor, this.presence, this.size = 36, this.fontSize = 14})`.
- `class PresenceBadge` — public `StatelessWidget` with public final fields `Presence presence`, `double size`, `bool showLabel`; const constructor `PresenceBadge({super.key, required this.presence, this.size = 10, this.showLabel = false})` and `static Color PresenceBadge.colorForPresence(Presence presence)`.

### Message rendering

- `class MessageBubble` — public `StatelessWidget` with a const constructor taking `super.key`, required `Message message`, required `bool isMine`, and optional `VoidCallback? onOpenThread`, `VoidCallback? onReplyInline`, `void Function(String emoji)? onToggleReaction`, `VoidCallback? onTogglePin`, `void Function(String newBody)? onEdit`, `VoidCallback? onDelete`, `void Function(Reaction reaction)? onShowReactionParticipants`, `String Function(String url)? fileUrlResolver`, `bool highlight = false`, `int deletedCount = 1`.
- `class MessageDeletedMarker` — public `StatelessWidget` with const constructor `MessageDeletedMarker({super.key, this.count = 1})` and public final field `int count`.
- `class MessageComposer` — public `StatefulWidget` with const constructor taking `super.key`, optional `Future<bool> Function(String body)? onSend`, optional `Future<List<(String, String)>?> Function()? onUploadAttachments`, optional `Future<bool> Function(String body, List<String>? attachmentIds)? onSendWithAttachments`, optional `ValueChanged<String>? onChanged`, `String initialText = ''`, optional `ValueChanged<bool>? onTyping`, `Message? replyTo`, `VoidCallback? onCancelReply`, and `String hintText = '메시지 보내기...'`.
- `class MessageAttachments` — public `StatelessWidget` with const constructor taking `super.key`, required `List<FileRef> attachments`, required `bool isMine`, and optional `String Function(String url)? fileUrlResolver`.

### Markdown rendering (`mobile/lib/widgets/message_markdown.dart`)

- `const quickReactions` — top-level `List<String>` of the 15 quick emojis (`'👍'` … `'☕'`), the same list as the desktop `QUICK_REACTIONS`.
- `class LinkTapRecognizer extends TapGestureRecognizer` — public final class with the getter `bool get isDisposed`.
- `List<InlineSpan> buildMessageSpans(String body, {TextStyle? baseStyle, Color? linkColor, Color? mentionColor, void Function(String url)? onLinkTap})` — top-level function that turns a message body into spans.
- `List<LinkTapRecognizer> linkRecognizersIn(List<InlineSpan> spans)` — top-level function that collects the link recognizers held by a span tree.
- `class MessageMarkdown extends StatefulWidget` — public final fields `String body`, `TextStyle? textStyle`, `Color? linkColor`, `Color? mentionColor`, `void Function(String url)? onLinkTap`; const constructor `MessageMarkdown({super.key, required this.body, this.textStyle, this.linkColor, this.mentionColor, this.onLinkTap})`.

## Invariants

- `[mobile/lib/widgets/app_snack_bar.dart:showAppSnackBar]` The `ScaffoldMessenger` path is taken only when `route is! PopupRoute && messenger != null`; a call from inside a modal (PopupRoute) instead goes to the root overlay so the snack bar is not hidden behind the modal. If the root overlay cannot be found, it falls back to `messenger?.showSnackBar(...)` so something still appears.
- `[mobile/lib/widgets/app_snack_bar.dart:showAppSnackBar]` The `SnackBarAction` is created only when both `actionLabel != null` and `onAction != null`; otherwise `action` is null.
- `[mobile/lib/widgets/app_snack_bar.dart:showAppSnackBar]` Both snack bar paths set `persist: false` so that the auto-dismiss duration is honored even when an action button is present (the action would otherwise switch the SnackBar to a persistent mode that ignores `duration`). The default `duration` is `const Duration(seconds: 4)`.
- `[mobile/lib/widgets/app_snack_bar.dart:_AppSnackBarHost.show]` A new message first calls `_remove()` so only one overlay snack bar is visible at a time; the `onDismiss` callback removes the entry only if `identical(_entry, entry)` is true, because an `OverlayEntry` may be removed only once.
- `[mobile/lib/widgets/app_snack_bar.dart:_AppSnackBarState._animationDuration]` The `AnimationController` uses `duration` and `reverseDuration` of `Duration(milliseconds: 180)`; the fade uses `Curves.easeOut` and the slide uses `Curves.easeOutCubic` moving from `Offset(0, 0.35)` to `Offset.zero`.
- `[mobile/lib/widgets/app_snack_bar.dart:_AppSnackBarState.initState]` The dismiss timer is created as `Timer(widget.duration, _dismiss)` right after `_controller.forward()`; the timer is cancelled and the `AnimationController` disposed in `dispose`.
- `[mobile/lib/widgets/app_snack_bar.dart:_AppSnackBarState._dismiss]` `_dismiss` returns early when `!mounted`, awaits `_controller.reverse()`, and returns early again on `!mounted` before calling `widget.onDismiss()`.
- `[mobile/lib/widgets/app_snack_bar.dart:_AppSnackBarState.build]` The bar is positioned at `bottom: keyboardInset` (`MediaQuery.of(context).viewInsets.bottom`) and `SafeArea` uses `bottom: keyboardInset == 0` so safe-area padding is not double-counted while the keyboard is open.
- `[mobile/lib/widgets/connection_banner.dart:isConnectionLost]` Returns `false` immediately when `state.isConnected`; otherwise returns true only when `state.connectionError != null` or the shared `_hasEverConnected` flag is true.
- `[mobile/lib/widgets/connection_banner.dart:_hasEverConnected]` A file-level shared `ValueNotifier<bool>` initialized to `false` records whether the realtime connection ever succeeded, so the shell banner and the channel/thread strip judge "never connected" vs "disconnected" consistently.
- `[mobile/lib/widgets/connection_banner.dart:_bannerMessage]` An empty or whitespace-only error returns the fixed text `'실시간 연결이 끊어졌습니다. 다시 연결하는 중입니다.'`. An error starting with `'세션이 만료'` is returned as-is. An error equal to `'연결이 끊어졌습니다.'` or containing `'실시간 연결이 끊어졌습니다'` is collapsed to the fixed reconnecting text. Any other error is prefixed to become `'실시간 연결이 끊어졌습니다. $text'`.
- `[mobile/lib/widgets/connection_banner.dart:_BannerContent.build]` The text uses `maxLines: singleLine ? 1 : null` and `overflow: singleLine ? TextOverflow.ellipsis : null`, so the strip truncates to one line while the shell banner allows wrapping.
- `[mobile/lib/widgets/llack_avatar.dart:LlackAvatar._getInitials]` An empty name yields `'?'`; a trimmed name of length 2 or less is returned as-is; otherwise only the first character uppercased is used.
- `[mobile/lib/widgets/llack_avatar.dart:LlackAvatar._resolveBgColor]` A non-empty `avatarColor` is parsed as hex after stripping a leading `'#'` and prefixed with `'FF'` for the alpha channel; any parse failure is swallowed and the color falls back to `LlackColors.avatarColorForName(name)`.
- `[mobile/lib/widgets/llack_avatar.dart:LlackAvatar.build]` The presence badge size is `size * 0.32` clamped with `.clamp(8.0, 14.0)`, positioned at `right: -1, bottom: -1` in a `Stack` with `clipBehavior: Clip.none`. When `presence == null` the avatar is wrapped in `Semantics(label: name, image: true)`; when presence is present the semantics label is `'$name, ${presence!.label}'`. A network image is used only when `avatarUrl != null && avatarUrl!.isNotEmpty`; otherwise the initials fallback is rendered, and `Image.network` also falls back to it via `errorBuilder`.
- `[mobile/lib/widgets/presence_badge.dart:PresenceBadge.colorForPresence]` Color mapping is exhaustive over the enum: `online` → `LlackColors.presenceOnline`, `busy` → `LlackColors.presenceBusy`, `dnd` → `LlackColors.presenceDnd`, `away` → `LlackColors.presenceAway`, `brb` → `LlackColors.presenceBrb`, `offline` → `LlackColors.presenceOffline`.
- `[mobile/lib/widgets/presence_badge.dart:PresenceBadge.build]` The dot is a circle of `size` with a 1.5-wide border of `LlackColors.paper`; when `showLabel` is false it is wrapped in `Semantics(label: presence.label)` so the color-only dot is announced as the status name, and when true a `Row` with a 5-wide gap shows `presence.label` in the status color.
- `[mobile/lib/widgets/message_bubble.dart:MessageBubble.build]` A message with `message.deletedAt != null` is rendered as only a `GestureDetector` wrapping `MessageDeletedMarker`, with no avatar, author, title, timestamp or bubble.
- `[mobile/lib/widgets/message_bubble.dart:MessageBubble.build]` The body is drawn with `MessageMarkdown` instead of a plain `Text`. On my own bubble the text style is `LlackTypography.body` recolored to `LlackColors.bubbleMineInk` and the link/mention colors are `LlackColors.bubbleMineInk` as well, so they stay legible on the orange bubble; on someone else's bubble the default `LlackTypography.body` and default accent colors are used.
- `[mobile/lib/widgets/message_bubble.dart:MessageBubble._showContextMenu]` The quick-emoji reaction row and the `'메시지 복사'` ListTile are only rendered when `message.deletedAt == null`; the `'메시지 수정'` and `'메시지 삭제'` ListTiles are only rendered when `isMine && message.deletedAt == null`. The quick-reaction emoji set is the shared `quickReactions` list (15 emojis) and each emoji button is a fixed 44-square.
- `[mobile/lib/widgets/message_bubble.dart:MessageBubble._wrapHighlight]` The highlight container (background `Color(0xFFFFF3D6)` with a 3px left border `Color(0xFFE8A33D)`) is applied only when `highlight` is true; otherwise the child is returned unchanged.
- `[mobile/lib/widgets/message_bubble.dart:MessageBubble.build]` The bubble width is constrained to `MediaQuery.sizeOf(context).width * 0.78`.
- `[mobile/lib/widgets/message_bubble.dart:MessageBubble._formatTimestamp]` The timestamp is formatted with `DeviceSettings.instance.clockFormat.value.format(dt)`, so it follows the device's 24-hour/12-hour setting instead of a hard-coded `'HH:mm'`.
- `[mobile/lib/widgets/message_bubble.dart:MessageBubble._showReactionParticipants]` When `onShowReactionParticipants` is supplied it is used, otherwise the widget falls back to `MessageActions.showReactionParticipants(context, reaction)` — the bubble itself never renders the participant sheet.
- `[mobile/lib/widgets/message_bubble.dart:MessageBubble._buildReplyQuote]` Returns `SizedBox.shrink()` when `message.replyTo == null`; the quoted author falls back to the literal `'답글'` when `replyTo.authorName.isEmpty` and the quoted body falls back to `'삭제된 메시지'` when `replyTo.deleted` is true.
- `[mobile/lib/widgets/message_bubble.dart:MessageBubble._buildReactionsRow]` Returns `SizedBox.shrink()` when `message.reactions.isEmpty` and each reaction chip is wrapped in a `ConstrainedBox` with `minHeight: 44`.
- `[mobile/lib/widgets/message_bubble.dart:MessageBubble._buildReactionsRow]` Long-pressing a reaction chip calls `HapticFeedback.mediumImpact()` and opens the participant list (the injected `onShowReactionParticipants` or the built-in fallback).
- `[mobile/lib/widgets/message_bubble.dart:MessageBubble._buildThreadButton]` Returns `SizedBox.shrink()` when `message.replyCount <= 0`, otherwise shows `'답글 ${message.replyCount}개'` inside a 44-min-height tap target.
- `[mobile/lib/widgets/message_bubble.dart:MessageBubble._showEditDialog]` The `onEdit` callback is invoked only when the new body `isNotEmpty` and differs from `message.body`.
- `[mobile/lib/widgets/message_bubble.dart:_EditMessageDialogState]` The `TextEditingController` is owned by the dialog state and is disposed in `dispose()` (dialog-scoped controllers are not auto-disposed); the save button reads `_controller.text.trim()` before calling `Navigator.pop(context)` and does not touch the controller after popping.
- `[mobile/lib/widgets/message_bubble.dart:MessageDeletedMarker.build]` The label is `'삭제된 메시지 $count개'` when `count > 1` and `'삭제된 메시지'` otherwise.
- `[mobile/lib/widgets/message_markdown.dart:quickReactions]` The list holds exactly 15 emojis and is identical to the desktop `QUICK_REACTIONS` in `desktop/src/lib/markdown.ts`; the composer's emoji grid and the bubble's reaction menu share it.
- `[mobile/lib/widgets/message_markdown.dart:buildMessageSpans]` The defaults are `LlackTypography.body` for the base style and `LlackColors.accentDeep` for both the link and the mention color.
- `[mobile/lib/widgets/message_markdown.dart:_parseBlocks]` The body is split on the ``` fence; the odd-indexed parts are code blocks and the even-indexed parts are parsed inline, so fences alternate exactly as on the desktop.
- `[mobile/lib/widgets/message_markdown.dart:_stripCodeFence]` A leading language line (matching `^[a-zA-Z0-9+#-]*\n`) and one trailing newline are removed from a code block.
- `[mobile/lib/widgets/message_markdown.dart:_parseInline]` Only a fixed set of marks is promoted — inline code, `**bold**`, `*italic*`, `~~strikethrough~~`, `http://`/`https://` links and `@mentions`; **raw HTML is never interpreted**, so `<b>굵게</b>` stays literal text.
- `[mobile/lib/widgets/message_markdown.dart:_parseInline]` Bold and strikethrough are promoted only when the inner text contains no further `*` / `~` and no newline; italics are promoted only when the `*` sits at the start of the text or after a space or `(`.
- `[mobile/lib/widgets/message_markdown.dart:_matchUrl]` A link runs until whitespace, `<` or `>`; trailing `. , : ; " ' ) ]` are trimmed off the address, and an address shorter than the scheme plus two characters is not a link.
- `[mobile/lib/widgets/message_markdown.dart:_matchMention]` A mention must start with an ASCII word character or a Hangul syllable and continue with at least one more word character, `.` or `-` (at most 30); a one-character mention such as `@a` is not a mention.
- `[mobile/lib/widgets/message_markdown.dart:_MessageMarkdownState.dispose]` The widget disposes the link recognizers itself, because `RichText` does not release the recognizers held by a `TextSpan`; `LinkTapRecognizer.isDisposed` makes that observable.
- `[mobile/lib/widgets/message_markdown.dart:_MessageMarkdownState.build]` Every build first disposes the recognizers of the previous build, so re-rendering the same body does not leak recognizers.
- `[mobile/lib/widgets/message_markdown.dart:_MessageMarkdownState._handleLinkTap]` When no `onLinkTap` callback is supplied the URL is copied to the clipboard and a snack bar reports it — the app has no `url_launcher` dependency, so the link is never opened directly.
- `[mobile/lib/widgets/message_composer.dart:_MessageComposerState.initState]` A non-empty `initialText` is restored into the controller (with the caret at the end) and enables the send button; `onChanged` is called once after the first frame so the parent is not mutated during build.
- `[mobile/lib/widgets/message_composer.dart:_MessageComposerState._updateCanSend]` The send state is enabled when the trimmed body is non-empty **or** at least one attachment is pending: an empty body with attachments can still be sent, and an empty body with no attachments cannot.
- `[mobile/lib/widgets/message_composer.dart:_MessageComposerState._handleSend]` Sending is skipped when `_isSending` is already true or when both the trimmed body and the attachment list are empty, and `_isSending` is set to true before awaiting the send callback to prevent duplicate sends. A pending upload is awaited first so the attachment ids are complete.
- `[mobile/lib/widgets/message_composer.dart:_MessageComposerState._handleSend]` `onSendWithAttachments` takes precedence over the legacy `onSend`; the attachment ids are passed as `null` when there are none. Any exception thrown by the callback is caught and treated as failure.
- `[mobile/lib/widgets/message_composer.dart:_MessageComposerState._handleSend]` After the await the method returns early if `!mounted`. On success the controller is cleared, the pending attachments and the emoji grid are cleared, the typing timer is cancelled and `onTyping(false)` is called; on failure the original text is restored into `_controller.text` with the selection collapsed to `offset: text.length`.
- `[mobile/lib/widgets/message_composer.dart:_MessageComposerState._handleTextChanged]` `onChanged` fires only when the text actually changed, so moving the caret alone does not notify; the send state is only updated via `setState` when the can-send state actually changes. The typing signal is reset by a `Timer` of `Duration(seconds: 3)` that calls `onTyping(false)`.
- `[mobile/lib/widgets/message_composer.dart:_MessageComposerState._insertEmoji]` An emoji replaces the current selection (or is inserted at the caret) and the field keeps the focus.
- `[mobile/lib/widgets/message_composer.dart:_MessageComposerState._upload]` A cancelled upload (`null`) adds no chip and a failed upload shows `'첨부를 올리지 못했습니다: …'` and also adds no chip.
- `[mobile/lib/widgets/message_composer.dart:_MessageComposerState.dispose]` The typing timer is cancelled and both the `TextEditingController` and the `FocusNode` are disposed.
- `[mobile/lib/widgets/message_composer.dart:_MessageComposerState.build]` The attach button is drawn only when `onUploadAttachments` is supplied, and the send button is enabled only when a send callback exists at all (`onSend` or `onSendWithAttachments`) in addition to the content check; while `_isSending` is true the icon is replaced by a `CircularProgressIndicator`. The input `TextField` uses `maxLines: 5` and `minLines: 1`; the send button container is a fixed 44x44 box and the reply-cancel IconButton has `BoxConstraints(minWidth: 44, minHeight: 44)`.
- `[mobile/lib/widgets/message_composer.dart:_MessageComposerState._buildEmojiGrid]` The grid lists the 15 `quickReactions` emojis in a 40x40 cell each, and tapping one inserts it into the text.
- `[mobile/lib/widgets/message_composer.dart:_MessageComposerState._buildReplyBanner]` The quoted body falls back to `'삭제된 메시지'` when `target.deletedAt != null`, and the banner text is limited to one line with ellipsis.
- `[mobile/lib/widgets/message_attachments.dart:MessageAttachments.build]` Returns `SizedBox.shrink()` when `attachments.isEmpty`.
- `[mobile/lib/widgets/message_attachments.dart:MessageAttachments._buildAttachment]` An attachment is treated as an image only when `file.mime.startsWith('image/')` and the resolved URL is non-empty; otherwise the file chip is rendered.
- `[mobile/lib/widgets/message_attachments.dart:MessageAttachments._authHeaders]` The `Authorization: Bearer $token` header map is only returned when the access token is non-null and non-empty; otherwise `null` is returned and the caller falls back to the file chip (the doc comment notes `GET /api/v1/files/{id}` returns 401 without auth). The provider read is wrapped in try/catch, so any failure results in a null token rather than an exception.
- `[mobile/lib/widgets/message_attachments.dart:MessageAttachments._buildImageAttachment]` If the auth headers are null the image is replaced by the file chip, and the `errorBuilder` of the network image also falls back to the file chip. The thumbnail is a fixed 160x120 `BoxFit.cover` image whose `loadingBuilder` draws an identically sized placeholder so the layout does not shift while loading.
- `[mobile/lib/widgets/message_attachments.dart:MessageAttachments._openImageViewer]` The fullscreen viewer uses `Dialog.fullscreen` with `InteractiveViewer(maxScale: 4)` and shows a `'이미지를 불러오지 못했습니다'` error state with the file name on load failure.
- `[mobile/lib/widgets/message_attachments.dart:MessageAttachments._formatSize]` Returns an empty string for `bytes <= 0`, `'B'` below 1024, `'KB'` below 1 MB and `'MB'` otherwise.
- `[mobile/lib/widgets/message_attachments.dart:MessageAttachments._buildFileChip]` The file name is constrained to `maxWidth: 150` with `maxLines: 1` and ellipsis overflow.

## Side Effects

- `[mobile/lib/widgets/app_snack_bar.dart:showAppSnackBar]` Reads the current route with `ModalRoute.of(context)` and the messenger with `ScaffoldMessenger.maybeOf(context)`; calls `messenger.hideCurrentSnackBar()` then `messenger.showSnackBar(...)`; in the overlay path reads the root overlay with `Overlay.maybeOf(context, rootOverlay: true)` and inserts an `OverlayEntry` via `overlay.insert(entry)`.
- `[mobile/lib/widgets/app_snack_bar.dart:_AppSnackBarHost._remove]` Removes the previously stored entry via `entry?.remove()` and clears `_entry`.
- `[mobile/lib/widgets/app_snack_bar.dart:_AppSnackBarState]` Starts the entry animation with `_controller.forward()`, reverses it with `await _controller.reverse()`, and runs a `Timer` that fires `_dismiss` after `widget.duration`. Tapping the snack bar body calls `_dismiss` immediately; tapping the action label invokes the supplied `onAction` callback.
- `[mobile/lib/widgets/connection_banner.dart:ConnectionBanner.build]` Reads app state with `context.watch<AppState>()` and mutates the shared `_hasEverConnected.value = true` when the connection is up.
- `[mobile/lib/widgets/connection_banner.dart:ConnectionBannerStrip.build]` Reads app state with `context.watch<AppState>()` and mutates the shared `_hasEverConnected.value = true` when the connection is up.
- `[mobile/lib/widgets/llack_avatar.dart:LlackAvatar.build]` Performs a network image fetch via `Image.network(avatarUrl!, ...)` with an `errorBuilder` fallback to the initials widget.
- `[mobile/lib/widgets/message_bubble.dart:MessageBubble._showContextMenu]` Long-pressing a bubble calls `HapticFeedback.mediumImpact()` and opens a `showModalBottomSheet` with `LlackColors.surfaceRaise` background; each context-menu item calls `Navigator.pop(ctx)` and `HapticFeedback.selectionClick()` before invoking `onToggleReaction`, `onOpenThread`, `onReplyInline` or `onTogglePin`. The `'메시지 복사'` item writes `message.body` to the clipboard via `Clipboard.setData(ClipboardData(text: message.body))` and then shows a `ScaffoldMessenger` SnackBar with the text `'복사되었습니다'` (1 second).
- `[mobile/lib/widgets/message_bubble.dart:MessageBubble._showEditDialog]` The `'메시지 수정'` item opens a `showDialog` hosting `_EditMessageDialog`; the delete item invokes the `onDelete` callback.
- `[mobile/lib/widgets/message_bubble.dart:MessageBubble._buildReactionsRow]` Tapping a reaction chip calls `HapticFeedback.selectionClick()` and invokes `onToggleReaction` with the reaction emoji; long-pressing it calls `HapticFeedback.mediumImpact()` and shows the participant list.
- `[mobile/lib/widgets/message_bubble.dart:MessageBubble._formatTimestamp]` Reads the device clock-format setting from `DeviceSettings.instance.clockFormat` (no I/O; the value is cached in the notifier).
- `[mobile/lib/widgets/message_bubble.dart:MessageBubble.build]` The bubble delegates attachment rendering to `MessageAttachments(attachments: message.attachments, isMine: ..., fileUrlResolver: fileUrlResolver)`; no network request is made directly by the bubble.
- `[mobile/lib/widgets/message_markdown.dart:_MessageMarkdownState._handleLinkTap]` Without an `onLinkTap` callback the URL is written to the clipboard with `Clipboard.setData(ClipboardData(text: url))` and a `ScaffoldMessenger` snack bar says `'링크를 복사했습니다: …'`.
- `[mobile/lib/widgets/message_markdown.dart:_MessageMarkdownState.dispose]` Disposes every `LinkTapRecognizer` the widget created, because `RichText` does not release span recognizers.
- `[mobile/lib/widgets/message_composer.dart:_MessageComposerState]` Sending calls the injected `widget.onSendWithAttachments(text, ids)` callback (or the legacy `widget.onSend(text)`) and awaits its `Future<bool>` result; every text change calls `widget.onTyping!(true)` and schedules `widget.onTyping?.call(false)` after the 3-second timer. On failure it calls `ScaffoldMessenger.of(context).showSnackBar` with the text `'전송에 실패했습니다. 다시 시도해주세요.'`. A text listener is registered on the `TextEditingController` via `_controller.addListener(_handleTextChanged)`, and the reply-cancel IconButton invokes `widget.onCancelReply`.
- `[mobile/lib/widgets/message_composer.dart:_MessageComposerState._pickAttachments]` The attach button calls the injected `widget.onUploadAttachments` callback to pick, upload and return the `(name, file id)` list; the widget itself performs no file I/O.
- `[mobile/lib/widgets/message_attachments.dart:MessageAttachments._authHeaders]` Reads the access token from provider state via `context.read<AppState>().api.accessToken`.
- `[mobile/lib/widgets/message_attachments.dart:MessageAttachments._buildImageAttachment]` Performs a network image load via `Image.network(url, headers: headers)` for the thumbnail; tapping it opens the fullscreen viewer.
- `[mobile/lib/widgets/message_attachments.dart:MessageAttachments._openImageViewer]` Opens a `showDialog` fullscreen viewer that issues another `Image.network(url, headers: headers)` request, with a close `IconButton` that calls `Navigator.pop(ctx)`.
- `[mobile/lib/widgets/message_attachments.dart:MessageAttachments._buildFileChip]` Tapping a file chip calls `ScaffoldMessenger.of(context)..hideCurrentSnackBar()..showSnackBar(...)` with the text `'이 파일은 데스크톱 앱에서 확인할 수 있습니다'` (no file-opening or URL-launch side effect).
- `[mobile/lib/widgets/message_attachments.dart:MessageAttachments._resolveUrl]` Resolves each attachment URL through the injected `fileUrlResolver` callback, falling back to the raw URL when no resolver is supplied.

## Verification

- Run: `flutter test` (from the `mobile/` directory)
- Widget-specific: `flutter test test/message_markdown_test.dart` (markdown parsing, the 15 quick reactions, recognizer disposal), `flutter test test/composer_attachments_test.dart` (upload / send-with-attachments / emoji grid / `onChanged`), `flutter test test/channel_draft_test.dart` (the restored `initialText`), `flutter test test/reaction_participants_test.dart` (long-press participant list).
