# Search Screens

## Overview

The global search dialog. It combines two sources:

- **Local** matches over the already-loaded channels, members, and projects,
  matched case-insensitively with `contains`.
- **Remote** message matches, fetched from
  `GET /workspaces/{id}/search?q=..&limit=30` after a 300 ms debounce.

Tapping a result navigates through `ChatNavigator` (channels and DMs) or
switches to the project tab, so the search dialog never pushes a route itself.

## Interface

- `class SearchSelection` — public class with public final fields `String? channelId`, `String? userId`, `String? projectId`, `String? messageId` and constructor `const SearchSelection({this.channelId, this.userId, this.projectId, this.messageId})` (`mobile/lib/screens/search/search_dialog.dart`).
- `class SearchDialog` — public `StatefulWidget` with `const SearchDialog({super.key})`; its private state class `_SearchDialogState` holds `_controller`, `_debounceTimer`, `_messageResults`, `_isSearching` and the request counter `_searchSeq`.

## Invariants

- `[mobile/lib/screens/search/search_dialog.dart:_SearchDialogState._onQueryChanged]` Search requests are debounced by 300 ms (`Timer(const Duration(milliseconds: 300), ...)`), and the pending timer is cancelled on every keystroke.
- `[mobile/lib/screens/search/search_dialog.dart:_SearchDialogState._onQueryChanged]` Each request carries a sequence number (`_searchSeq`) and a response is discarded when `!mounted || seq != _searchSeq`, because cancelling the debounce timer does not cancel an already-sent HTTP request. Clearing the query increments `_searchSeq` and clears `_messageResults` and `_isSearching`, so in-flight responses are discarded.
- `[mobile/lib/screens/search/search_dialog.dart:_SearchDialogState._onQueryChanged]` Search errors are swallowed silently and the previous results are kept; `_isSearching` is reset in `finally` only when the widget is mounted and the sequence still matches.
- `[mobile/lib/screens/search/search_dialog.dart:_SearchDialogState.build]` Local channel, member and project filtering is a case-insensitive `contains` match on the lower-cased query (channel name; user name, email and title; project name).
- `[mobile/lib/screens/search/search_dialog.dart:_SearchDialogState.build]` The current user is excluded from the member results because opening a 1:1 DM with oneself is rejected by the server with 422.
- `[mobile/lib/screens/search/search_dialog.dart:_SearchDialogState.build]` The `'검색 결과가 없습니다'` empty state is only shown when there are no results at all and `_isSearching` is false; the dialog is constrained to `maxWidth: 520, maxHeight: 580`.

## Side Effects

- `[mobile/lib/screens/search/search_dialog.dart:_SearchDialogState._onQueryChanged]` After the 300 ms debounce calls `state.search(query)` — `GET /workspaces/$workspaceId/search?q=<encoded>&limit=30`. It creates and cancels a `Timer` for each keystroke; the timer is cancelled again in `dispose` along with the `TextEditingController` disposal.
- `[mobile/lib/screens/search/search_dialog.dart:_SearchDialogState.build]` The channel result tap calls `Navigator.pop(context, SearchSelection(channelId: c.id))` and then `ChatNavigator.openChannel(...)`, which selects the channel and pushes `MaterialPageRoute(builder: (_) => const ChatScreen(showBackButton: true))` when the form factor is compact.
- `[mobile/lib/screens/search/search_dialog.dart:_SearchDialogState.build]` The member result tap calls `Navigator.pop(context, SearchSelection(userId: m.user.id))` and then `ChatNavigator.openDm(...)`, which POSTs `/workspaces/$workspaceId/dms` and pushes the `ChatScreen` route when compact. On DM failure it captures `ScaffoldMessenger.of(context)` before the await and calls `messenger.showSnackBar(SnackBar(content: Text(ChatNavigator.describeDmError(error))))`.
- `[mobile/lib/screens/search/search_dialog.dart:_SearchDialogState.build]` The project result tap calls `Navigator.pop(context, SearchSelection(projectId: p.id))`, awaits `appState.selectProject(p)` — which loads `GET /projects/$projectId/tasks`, `/projects/$projectId/roadmaps` and `/projects/$projectId/milestones` — then calls `appState.goToTab(2)` to switch to the project tab.
- `[mobile/lib/screens/search/search_dialog.dart:_SearchDialogState.build]` The message result tap calls `Navigator.pop(context, SearchSelection(channelId: r.channel.id, messageId: r.message.id))` and then `ChatNavigator.openChannel(..., messageId: r.message.id)`, which selects the channel with `focusMessageId` and pushes the `ChatScreen` route.
- `[mobile/lib/screens/search/search_dialog.dart:_SearchDialogState.build]` Reads provider state via `context.watch<AppState>()` (allChannels, members, projects, currentUser, getPresence) and `context.read<AppState>()` inside the tap handlers.

## Verification

- Run: `flutter test` (from the `mobile/` directory)
