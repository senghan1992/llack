# EGM Drift Report — Llack
대상: `egm-bootstrap` 이 생성·수정한 EGM 계약 34개 (`2026-11-12` 기준).
방법:
1. **문서 → 코드** — 계약에 적힌 코드 인용 2,053건을 전부 기계적으로 확인했습니다(파일 존재 여부 + 심볼 실재 여부). 파일 없음 0건, 심볼 미확인 1건(위 표기 문제).
2. **코드 → 문서** — 코드에서 공개 심볼·라우트·테이블을 뽑아 해당 계약에 실제로 적혀 있는지 대조했습니다. 대상: FastAPI 라우트 80개, Tauri 커맨드 5개, ORM 테이블 21개, 서비스 모듈 함수 25개, ORM/스키마 클래스 81개, Dart 클래스 103개, TS/TSX export 119개.
아래는 **차이만** 적었습니다. 차이가 없는 문서에는 "No drift detected" 라고만 쓰고, 일치하는 내용을 옮겨 적지 않았습니다.
---
## README.md
No drift detected.

## backend/README.md
- **표기 문제 (계약 내용과 무관).** `[backend/docker-entrypoint.sh:docker-entrypoint.sh]` 는 심볼 자리에 파일명 자체를 넣은 인용입니다. 파일은 존재하고 내용(`set -eu`, `exec "$@"`)도 정확히 적혀 있으나, 다른 인용들이 쓰는 `파일:심볼` 관례와 어긋납니다. 이 파일에는 이름 붙은 심볼이 없어(`set -eu` 와 `exec "$@"` 뿐) 그대로 두었습니다.

## backend/app/README.md
No drift detected.

## backend/app/api/README.md
No drift detected.

## backend/app/api/v1/README.md
No drift detected.

## backend/app/core/README.md
No drift detected.

## backend/app/models/README.md
No drift detected.

## backend/app/realtime/README.md
No drift detected.

## backend/app/schemas/README.md
No drift detected.

## backend/app/services/README.md
- **미해결 → 수정함.** `messages.py` 의 커서 비교 도우미 `_newer_than` 이 계약에 없었습니다. 짝이 되는 `_older_than` 은 Invariants 절에 인용되어 있었고, 두 도우미는 대칭입니다(`created_at` 비교 + 동률일 때 `id` 비교). `_older_than` 인용 바로 아래에 `_newer_than` 을 추가했습니다.

## backend/scripts/README.md
No drift detected.

## desktop/README.md
No drift detected.

## desktop/src/README.md
No drift detected.

## desktop/src/components/README.md
- **미해결 → 수정함.** `Dialogs.tsx` 가 공개로 export 하는 대화상자 12개 중, Interface 절에 적힌 것은 `Dialog` 하나뿐이었습니다. `SearchDialog`, `PaletteDialog`, `NewChannelDialog`, `PeopleDialog`, `NewDmDialog`, `PinsDialog`, `ChannelSettingsDialog`, `InviteDialog`, `AddPeopleDialog`, `LeaveChannelDialog`, `DeleteDmDialog` 의 11개가 Interface 절에서 빠져 있었습니다. 그중 `NewChannelDialog`, `NewDmDialog`, `PinsDialog`, `AddPeopleDialog`, `LeaveChannelDialog`, `DeleteDmDialog` 6개는 파일 어디에도 등장하지 않아 계약에 전혀 없었습니다. Interface 절에 11개를 추가하고, 없던 6개의 Invariants·Side Effects 항목도 `Dialogs.tsx` 원문(`desktop/src/components/Dialogs.tsx:492`, `:694`, `:749`, `:1063`, `:1154`, `:1204`)을 읽고 근거를 적어 넣었습니다.

## desktop/src/lib/README.md
No drift detected.

## desktop/src/store/README.md
No drift detected.

## desktop/src-tauri/README.md
No drift detected.

## desktop/src-tauri/src/README.md
No drift detected.

## mobile/README.md
No drift detected.

## mobile/lib/README.md
No drift detected.

## mobile/lib/models/README.md
No drift detected.

## mobile/lib/providers/README.md
No drift detected.

## mobile/lib/responsive/README.md
No drift detected.

## mobile/lib/screens/README.md
No drift detected.

## mobile/lib/screens/chat/README.md
No drift detected.

## mobile/lib/screens/org/README.md
No drift detected.

## mobile/lib/screens/projects/README.md
No drift detected.

## mobile/lib/screens/schedule/README.md
No drift detected.

## mobile/lib/screens/search/README.md
No drift detected.

## mobile/lib/screens/settings/README.md
No drift detected.

## mobile/lib/services/README.md
No drift detected.

## mobile/lib/theme/README.md
No drift detected.

## mobile/lib/widgets/README.md
No drift detected.

## scripts/README.md
No drift detected.

