---
name: Llack
description: 하루 종일 켜두는 사내 협업 도구 — 무광 안내판 위에 1px 罫線으로만 구획된, 단 하나의 색을 아끼는 밝은 업무 표면.
colors:
  n0: "#ffffff"
  n1: "#fafaf9"
  n2: "#f4f4f2"
  n3: "#ededea"
  n4: "#e4e4e0"
  n5: "#dededa"
  n6: "#c2c2bc"
  n7: "#8f8f89"
  n8: "#6a6a64"
  n9: "#55554f"
  n10: "#16171a"
  board: "#ededea"
  field: "#fafaf9"
  paper: "#ffffff"
  hover: "rgba(22, 23, 26, 0.045)"
  ink: "#16171a"
  ink-secondary: "#55554f"
  ink-muted: "#6a6a64"
  ink-inverse: "#ffffff"
  rule: "#c2c2bc"
  rule-strong: "#8f8f89"
  signal: "#a50034"
  signal-press: "#86002a"
  signal-wash: "#fbf0f3"
  signal-select: "rgba(165, 0, 52, 0.14)"
  tint-a: "#ededea"
  tint-b: "#e4e4e0"
  tint-c: "#dededa"
  tint-d: "#c2c2bc"
typography:
  display:
    fontFamily: "Pretendard, -apple-system, BlinkMacSystemFont, \"Apple SD Gothic Neo\", \"Segoe UI\", \"Noto Sans KR\", \"Malgun Gothic\", sans-serif"
    fontSize: "21px"
    fontWeight: 700
    lineHeight: 1.55
    letterSpacing: "-0.03em"
  title:
    fontFamily: "Pretendard, -apple-system, BlinkMacSystemFont, \"Apple SD Gothic Neo\", \"Segoe UI\", \"Noto Sans KR\", \"Malgun Gothic\", sans-serif"
    fontSize: "14px"
    fontWeight: 600
    lineHeight: 1.55
    letterSpacing: "-0.014em"
  body:
    fontFamily: "Pretendard, -apple-system, BlinkMacSystemFont, \"Apple SD Gothic Neo\", \"Segoe UI\", \"Noto Sans KR\", \"Malgun Gothic\", sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: "-0.006em"
    fontFeature: "tabular-nums"
  body-strong:
    fontSize: "13px"
    fontWeight: 600
    lineHeight: 1.55
    letterSpacing: "-0.012em"
  secondary:
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: "-0.006em"
  meta:
    fontSize: "11px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontSize: "10px"
    fontWeight: 600
    lineHeight: 1.6
    letterSpacing: "0.07em"
  mono:
    fontFamily: "ui-monospace, \"SF Mono\", \"JetBrains Mono\", D2Coding, Menlo, Consolas, monospace"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.5
rounded:
  plate: "2px"
  dot: "50%"
spacing:
  xs: "4px"
  sm: "6px"
  md: "8px"
  lg: "12px"
  xl: "14px"
  gutter: "40px"
  count-column: "46px"
  rail-tail: "18px"
components:
  button-primary:
    backgroundColor: "{colors.signal}"
    textColor: "{colors.ink-inverse}"
    typography: "{typography.secondary}"
    rounded: "{rounded.plate}"
    padding: "0 10px"
    height: "26px"
  button-primary-hover:
    backgroundColor: "{colors.signal-press}"
    textColor: "{colors.ink-inverse}"
  button-primary-disabled:
    backgroundColor: "{colors.n4}"
    textColor: "{colors.ink-muted}"
  button-icon:
    textColor: "{colors.ink-muted}"
    rounded: "{rounded.plate}"
    size: "26px"
  button-icon-hover:
    backgroundColor: "{colors.hover}"
    textColor: "{colors.ink}"
  input-field:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.plate}"
    padding: "0 9px"
    height: "42px"
  input-composer:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.plate}"
    padding: "6px 6px 6px 10px"
  row-channel:
    backgroundColor: "{colors.board}"
    textColor: "{colors.ink-secondary}"
    typography: "{typography.body}"
    padding: "0 12px"
    height: "26px"
  row-channel-active:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.body-strong}"
  badge-count:
    backgroundColor: "{colors.n5}"
    textColor: "{colors.ink-secondary}"
    typography: "{typography.label}"
    rounded: "{rounded.plate}"
    padding: "0 4px"
  badge-mention:
    backgroundColor: "{colors.signal}"
    textColor: "{colors.ink-inverse}"
  chip-tag:
    textColor: "{colors.ink-muted}"
    typography: "{typography.label}"
    rounded: "{rounded.plate}"
    padding: "0 4px"
  avatar-plate:
    backgroundColor: "{colors.tint-b}"
    textColor: "{colors.ink-secondary}"
    rounded: "{rounded.plate}"
    size: "20px"
  banner-error:
    backgroundColor: "{colors.signal-wash}"
    textColor: "{colors.signal}"
    typography: "{typography.secondary}"
    padding: "6px 10px 6px 14px"
  banner-info:
    backgroundColor: "{colors.n2}"
    textColor: "{colors.ink-secondary}"
  palette-sheet:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    width: "min(620px, 92vw)"
  notice:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.secondary}"
    rounded: "{rounded.plate}"
    padding: "9px 4px 10px 12px"
    width: "320px"
  notice-mention:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
---

# Design System: Llack

## Overview

**Creative North Star: "안내판(The Departure Board)"**

Llack 의 표면은 역·공항의 시각표입니다. 열은 절대 움직이지 않고 행만 살아 움직입니다. 채널 목록의 각 행은 [표식][이름][수치] 이라는 고정된 칸에 값을 넣는 자리이고, 채널 이름이 길어져도 안 읽음 숫자가 있던 자리는 그대로입니다. 하루 여덟 시간 켜두는 도구가 사용자에게 갚아야 할 것은 "매번 같은 좌표"이며, 이 시스템의 모든 결정은 그 한 문장에서 나옵니다.

재질은 무광입니다. 카드가 없고, 둥근 패널이 없고, 쌓임(elevation)이 없습니다. 구획은 오로지 1px 罫線 하나로 합니다 — 헤더와 전사록, 레일과 본문, 컴포저와 스크롤 영역이 모두 같은 굵기의 선 한 줄로 나뉩니다. 예외는 정말로 떠 있는 물체들뿐입니다 — 커맨드 팔레트, 멘션 피커, "최신으로" 버튼, 그리고 우하단 알림 토스트가 진짜 오프셋+블러 그림자를 갖습니다. 색은 무채색 11단 램프 하나가 전부이고, 그 위에 LG Red(`--signal`) 한 색이 오직 "나를 향한 것"과 "내가 지금 있는 곳"에만 나타납니다. 표면이 붉어지는 순간은 언제나 볼 가치가 있는 순간입니다.

밝은 사무실, 다른 밝은 사내 도구 옆에서 종일 쓰는 장면을 기준으로 light-first 로 만들었습니다. 다크 테마는 이 빌드에 없습니다 — 다만 램프가 반전 가능한 형태로 authored 되어 있어, 컴포넌트 규칙을 건드리지 않고 `--n0`…`--n10` 만 뒤집어 도입할 수 있습니다. 이는 구현된 기능이 아니라 지켜야 할 경계로 기록합니다.

**Key Characteristics:**
- 11단 무채색 램프(`--n0`…`--n10`)가 유일한 톤 토큰. 램프에 없는 값은 버그입니다.
- 바탕은 두 값의 분할: `--field`(전사록·시트, `--n1`)와 `--board`(도크·레일·사인인, `--n3`).
- 1px 罫線이 유일한 구획 수단. 카드·둥근 패널·상시 그림자 없음.
- 신호색은 하나, 의미도 하나. 안 읽음은 색이 아니라 굵기입니다.
- 상태는 형태로 표현: 프레즌스는 채움/테두리/막힘, 색조를 쓰지 않습니다.
- 단일 자체 호스팅 서체(Pretendard variable), `body` 전역 tabular 숫자.
- 열은 고정 폭, 행만 변합니다. 스레드는 덮지 않고 옆으로 밀어 열립니다.
- authored 모션은 셋: 도킹 시트(200ms) · 알림 진입(180ms) · 수치 플랩(160ms). 공통 조건은 "도착을 알린다" 하나입니다.

## Colors

무광 종이 같은 따뜻한 회색 11단 위에, 진한 자적(赤紫) 하나만 아껴 쓰는 팔레트입니다.

### Primary
- **시그널 레드 / LG Red** (`--signal`): 표면에서 유일한 유채색. 쓰이는 자리는 다섯 곳으로 끝입니다 — 멘션 배지와 `@나` 멘션, 오류 배너, 키보드 포커스 링과 캐럿, 주 동작 버튼(보내기·로그인·앱 설치), "내가 지금 있는 곳"(선택된 행의 `#`/잠금 표식, 활성 도크 타일의 2px 밑줄), 그리고 나를 향한 알림 토스트의 왼쪽 1px 선. `--field` 위 7.2:1.
- **시그널 프레스** (`--signal-press`): 주 동작 버튼의 hover/press 상태 단 하나.
- **시그널 워시** (`--signal-wash`): 나를 향한 메시지 행과 오류 배너가 앉는 바탕. 항상 1px `--signal` 안쪽 선을 동반합니다.
- **시그널 셀렉트** (`--signal-select`): 텍스트 선택(`::selection`) 배경. 잉크 색은 그대로 유지합니다.

### Neutral
- **보드** (`--board` = `--n3`): 무광 안내판 바탕. 좌측 도크, 채널 레일, 사인인 화면의 바탕입니다.
- **필드** (`--field` = `--n1`): 불 켜진 판. 전사록, 스레드 시트, 앱 패널, 사인인 플레이트의 바탕.
- **페이퍼** (`--paper` = `--n0`): 입력 가능한 것과 선택된 것에만 씁니다 — 입력칸, 선택된 채널 행, 활성 도크 타일, 커맨드 팔레트, 리액션·첨부 칩.
- **호버** (`--hover`): 잉크의 4.5% 알파. 모든 행·타일·아이콘 버튼의 hover 는 이 한 값입니다.
- **잉크** (`--ink` = `--n10`): 본문, 강조된 이름, 안 읽음 행, 선택된 행.
- **잉크 세컨더리** (`--ink-secondary` = `--n9`): 평상 행 라벨, 앱 메시지 본문, 보조 설명. `--field` 위 6.8:1.
- **잉크 뮤티드** (`--ink-muted` = `--n8`): 가장 작은 글자 전부 — 메타, 시각, 섹션 라벨, 플레이스홀더. 시스템의 모든 바탕에서 4.6:1 이상.
- **잉크 인버스** (`--ink-inverse` = `--n0`): 시그널 위에 얹히는 글자에만.
- **罫線** (`--rule` = `--n6`): 영역 분할과 순수 장식 경계(도크 구분선, 스피너 트랙, `kbd` 키캡).
- **강한 罫線** (`--rule-strong` = `--n7`): 조작 가능한 것과 상태의 경계 — 입력 테두리, 선택 행의 안쪽 선, 스크롤바 썸, 태그, 밑줄. `--field` 위 3.1:1(AA non-text).
- **플레이트 틴트** (`--tint-a`…`--tint-d` = `--n3`/`--n4`/`--n5`/`--n6`): 아바타 판의 네 단계. 색상환이 아니라 램프의 네 칸입니다.

### Named Rules

**The One Colour, One Meaning Rule.** `--signal` 은 "당신을 향한 신호"와 "당신이 있는 곳"만 뜻합니다. 멘션·오류·포커스·주 동작·현재 위치·나를 향한 토스트, 이 여섯 자리 밖에서 붉은색이 나오면 그것은 팔레트 누수입니다. 새 표면이 "나를 향한 것"을 표시할 때는 새 장치를 만들지 말고 전사록의 멘션 행이 쓰는 왼쪽 1px 시그널 선을 그대로 물려받으십시오 — 알림 토스트가 그렇게 했습니다.

**The Unread Is Weight Rule.** 평범한 안 읽음은 색을 쓰지 않습니다. `font-weight: 600` 과 `--ink` 로만 표시합니다. 색을 쓰는 안 읽음은 나에게 온 멘션 하나뿐입니다.

**The Eleven Steps Rule.** 모든 톤은 `--n0`…`--n10` 에서 나옵니다. 램프에 없는 회색 값을 새로 적는 것은 버그입니다(신호 계열 4개와 `--hover` 알파만 예외).

**The Reserved Hue Rule.** 아바타·프레즌스·태그·상태는 유채색을 쓸 수 없습니다. 설치된 미니앱이 자신의 `accent_color` 를 신고해도 표면은 이를 의도적으로 무시하고 `--ink-muted` 점으로 렌더합니다.

## Typography

**Body Font:** Pretendard Variable (자체 호스팅 `@font-face`, `font-weight: 300 800`, `font-display: swap`) — 폴백은 플랫폼 sans, 그다음 이모지 패밀리.
**Label/Mono Font:** `ui-monospace` 스택(SF Mono / JetBrains Mono / D2Coding / Menlo / Consolas) — 인라인 코드·코드 블록, 그리고 보드의 [수치] 필드(채널 배지·도크 배지)에.

**Character:** 서체는 하나뿐입니다. 오프라인 Tauri 창에서 CDN 은 해석되지 않고, 플랫폼 sans 로 떨어지면 OS 마다 다른 얼굴이 되므로 variable woff2 한 파일을 직접 싣습니다. 한글이 조밀하게 서는 얼굴에 음수 자간을 얹어, 13px 본문이 밀도 높게 붙되 답답하지 않게 읽힙니다. 이모지 패밀리를 스택 맨 뒤에 두는 것은 장식이 아니라 기능입니다 — 누군가 실제로 쓴 🙏 가 `.notdef` 상자로 그려지면 안 됩니다.

### Hierarchy
- **Display** (700, 21px, `letter-spacing: -0.03em`): 사인인 화면의 제품명 한 곳. 제품 안에는 등장하지 않습니다.
- **Title** (600, 14px, `-0.014em`): 채널 헤더의 `h1`. 표면에서 가장 큰 제품 내 글자입니다.
- **Body** (400, 13px/1.55, `-0.006em`): 메시지 본문, 입력칸, 팔레트 결과 라벨, 채널 행 라벨. 본문 폭은 `max-width: 72ch`(65–75ch 대역) 로 제한하고, 시트가 도킹되면 자연히 더 좁아집니다.
- **Body Strong** (600, 13px, `-0.012em`): 작성자 이름, 워크스페이스 이름, 안 읽음/선택 행.
- **Secondary** (400, 12px): 패널 헤더, 버튼 라벨, 보조 설명, 코드.
- **Meta** (400, 11px): 시각, 개수, 토픽, 힌트, 프레즌스 문구.
- **Label** (600, 10px, `0.07em`, 대문자): 섹션 머리, 날짜 구분선, 팔레트 종류 칸. 대문자 트래킹 라벨은 이 10px 한 단계에만 허용됩니다.
- **Field name** (600, 9px, `0.06em`, `--n7`, 우측 정렬): 보드의 열 이름(`안 읽음`) 단 하나의 용도. 섹션 머리보다 한 단계 작고 옅어, 이름표가 값보다 먼저 읽히지 않습니다.
- **Count** (mono, 600, 10px, `tabular-nums`): 채널·도크 배지의 숫자. 보드의 수치 칸은 본문 서체가 아니라 mono 로 셉니다.

### Named Rules

**The One Face Rule.** 표면 전체가 Pretendard 한 얼굴입니다. 새로운 서체, 굵기 축 밖의 합성 볼드/이탤릭, 디스플레이용 두 번째 얼굴을 들이지 않습니다.

**The Fixed Cell Numbers Rule.** `font-variant-numeric: tabular-nums` 는 `body` 전역입니다. 안 읽음 숫자가 3 에서 12 로 바뀔 때 행의 어떤 것도 밀려서는 안 됩니다.

**The Counted Figures Set In Mono Rule.** 보드의 [수치] 필드는 `--font-mono` 로 셉니다(배지 10px/600 + `tabular-nums`). 세는 숫자와 읽는 글이 같은 서체로 서면 열이 열로 읽히지 않습니다. 시각·상대시간처럼 문장 안에서 읽히는 숫자는 계속 본문 서체입니다.

**The Eight Steps Of Size Rule.** 실제로 쓰이는 크기는 21 / 15(팔레트 입력) / 14 / 13 / 12 / 11 / 10 px 입니다. 그 사이의 새 크기를 만들지 말고 가장 가까운 단계를 쓰십시오.

## Layout

셸은 3열 그리드입니다: `52px` 도크 · `260px` 채널 보드 · `minmax(0, 1fr)` 본문. 행은 `minmax(0, 1fr)` 하나로 명시되어 있어 창 전체가 스크롤되지 않고 각 판이 자기 안에서 스크롤합니다. 헤더 높이는 전 영역 공통 `44px` 이고 아래로 1px 罫線 한 줄만 그립니다. 컴포저는 하단 고정입니다.

시트는 본문 오른쪽에 도킹됩니다 — 스레드 `340px`, 앱 패널 `380px`. 둘 다 전사록을 덮지 않고 좁힙니다. 이것이 제품의 구조적 약속이므로 유일한 authored 모션도 여기에 씁니다.

행 리듬: 채널 행 `26px`, 도크 타일 `34px`, 아이콘 버튼 `26px`(패널 헤더는 `24px`), 팔레트 결과 행 `30px`, 사인인 입력 `42px`. 여백은 4 / 6 / 8 / 12 / 14 px 이 전부이고, 레일 안쪽 여백은 12px, 전사록 안쪽 여백은 14px 입니다. 메시지 거터는 `40px`(좁은 창에서 `34px`).

채널 행은 네 트랙입니다: `16px minmax(0, 1fr) var(--count-w) var(--rail-tail)` (`--count-w: 46px`, `--rail-tail: 18px`) — 첫 칸이 표식과 구분을 겸하고(채널은 `#`/잠금, DM 은 20px 아바타), 이름은 남는 폭을 먹고 줄임표로 잘리고, 수치는 46px 고정 칸의 오른쪽에 붙고(`justify-self: end`), 마지막 트랙은 의도적으로 빈 꼬리입니다. 채널 행에 별도의 상태 칸은 없습니다.

`--rail-tail` 이 존재하는 이유는 하나입니다: 채널 추가 컨트롤이 머리 행의 오른쪽 끝에 앉으면서도 수치 열을 밀어내지 않게 하는 것. 행에서는 비어 있고, ≤720px 스트립에서는 `0px` 로 접힙니다.

섹션 머리(`.sidebar-section h2`)가 곧 열 이름 행입니다 — 같은 네 트랙 위에서 `채널 … 안 읽음 +` 로 서고, 추가 컨트롤은 네 번째 트랙에 배치됩니다. 이미 있던 24px 머리 행을 재사용하므로 높이 비용은 0 이며, 필드에 이름이 붙는 순간 좌측 레일은 목록이 아니라 안내판으로 읽힙니다. 실측: 머리 행 이름표의 우변과 배지의 우변이 모두 274px(델타 0).

반응형은 네 단계이고, 어느 단계에서도 사용자가 방금 연 것을 조용히 없애지 않습니다.
- **≤1180px**: 시트만 좁힙니다(`--thread-w: 300px`, `--panel-w: 320px`).
- **≤960px**: 레일 `216px`. 스레드와 앱 패널이 동시에 열려 있으면 오른쪽 `288px` 한 열에 위아래로 명시 배치되고, 모든 트랙과 아이템이 명시적으로 지정됩니다.
- **≤860px**: 채널 토픽만 숨깁니다(맥락이지 이동 수단이 아니므로 먼저 나갑니다).
- **≤720px**: 셸이 세로로 쌓이고 채널 보드가 가로 스트립이 됩니다. 여전히 순위가 있는 행의 나열이며, 방향만 바뀝니다. Tauri 창이 `minWidth: 940` 을 강제하므로 이 구간은 브라우저 리뷰 경로에서만 나타납니다.

### Named Rules

**The Columns Never Move Rule.** 열 폭은 토큰이고 행만 변합니다. 콘텐츠 길이에 따라 트랙 폭이 재계산되는 레이아웃(`auto` 열, 암시적 그리드 트랙)을 새로 만들지 마십시오.

**The Named Field Needs A Fixed Track Rule.** 열에 이름을 붙이려면 그 트랙이 먼저 고정 폭이어야 합니다. 머리 행과 그 아래 행들은 서로 다른 그리드이므로 `auto` 트랙은 각자의 콘텐츠에 맞춰지고, 그러면 열 이름이 자기가 덮지 않는 열을 가리키게 됩니다. 이름표를 붙이는 검사는 한 줄입니다: 이름표의 우변과 값의 우변이 같은 px 인가.

**The Nothing Disappears Rule.** 좁아질 때 기능을 숨겨 해결하지 않습니다. 스택하거나, 축을 바꾸거나, 폭을 줄입니다. 숨겨도 되는 것은 순수한 맥락 텍스트(토픽, 멤버 수)뿐입니다.

**The Push, Never Cover Rule.** 스레드와 앱 패널은 전사록을 좁히며 옆에 섭니다. ≤720px 에서만 같은 모서리에서 도착해 덮으며, 그때도 자기 헤더에 닫기 컨트롤을 갖고 있습니다.

## Elevation & Depth

이 시스템은 쌓이지 않습니다. 깊이는 그림자가 아니라 세 가지로 표현됩니다: 1px 罫線, `--board`→`--field`→`--paper` 세 단계의 값(무광 판 → 불 켜진 판 → 만질 수 있는 종이), 그리고 안쪽 1px 선(`inset 0 0 0 1px`)입니다. 선택된 채널 행과 활성 도크 타일이 "떠 보이는" 것은 그림자가 아니라 `--paper` 로 올라서고 `--rule-strong` 안쪽 선을 얻기 때문입니다.

그림자가 허용되는 것은 실제로 떠 있는 물체 세 개뿐이며, 모두 오프셋과 블러를 가진 진짜 드리운 그림자입니다(하드 오프셋 그림자, 헤일로, 컬러 글로우 금지).

### Shadow Vocabulary
- **Floating sheet** (`box-shadow: 0 16px 44px rgba(22, 23, 26, 0.16)`): 커맨드 팔레트와 모달. 표면에서 유일한 진짜 고도.
- **Popover** (`box-shadow: 0 6px 20px rgba(22, 23, 26, 0.1)`): 컴포저 위에 뜨는 멘션 피커.
- **Notice float** (`box-shadow: 0 6px 20px rgba(22, 23, 26, 0.14)`): 우하단 알림 토스트. 팝오버와 같은 문법(오프셋+블러), 값만 한 단계 진합니다. 나를 향한 토스트는 여기에 `inset 2px 0 0 -1px var(--signal)` 을 겹쳐 씁니다.
- **Anchored control** (`box-shadow: 0 2px 8px rgba(22, 23, 26, 0.08)`): 전사록 위에 떠 있는 "최신으로" 버튼.
- **Inset boundary** (`box-shadow: inset 0 0 0 1px var(--rule-strong)`): 고도가 아니라 상태 경계. 선택된 행, 활성 도크 타일.
- **Inset signal edge** (`box-shadow: inset 1px 0 0 var(--signal)` / `inset 2px 0 0`): 멘션 행, 팔레트 활성 행, 오류 배너. 색만으로 상태를 말하지 않기 위한 동반 선입니다.
- **Backdrop** (`background: rgba(22, 23, 26, 0.28)`): 모달 뒤 바탕. 블러 없음.

### Named Rules

**The Rules, Not Cards Rule.** 영역은 1px 罫線으로 나눕니다. 카드, 둥근 패널, 상시 그림자, 쌓인 컨테이너를 만들지 마십시오. 사인인 화면조차 카드가 아니라 보드에 붙은 플레이트입니다(위 `--ink` 선, 아래 `--rule` 선).

**The Only Floaters Cast Shadows Rule.** 그림자는 정말로 표면에서 떨어져 있는 것만 갖습니다 — 현재 넷입니다: 팔레트/모달, 멘션 피커, "최신으로" 버튼, 알림 토스트. 앉아 있는 것은 값과 선으로 구분됩니다. 다섯 번째를 더하려면 그것이 진짜로 떠 있는지 먼저 증명해야 하고, 그림자는 반드시 기존 오프셋+블러 문법을 재사용해야 합니다(헤일로·글로우·하드 오프셋 금지).

**The Measured Bottom Rule.** 하단 모서리에 붙는 floater 는 컴포저를 측정해서 피합니다. 컴포저는 여러 줄 초안에서 자라므로 고정 오프셋은 언젠가 보내기 버튼을 덮습니다. `ResizeObserver` 로 `.main-transcript .composer` 높이를 재고, "최신으로" 버튼이 떠 있으면 그 높이까지 더한 뒤 14px 모서리 여백을 붙여 `bottom` 을 계산합니다. CSS 의 `bottom: 14px` 는 측정 전 폴백일 뿐입니다.

## Shapes

형태 언어는 "판(plate)"입니다. 모서리 반경은 시스템 전체에 `--r: 2px` 하나이고, 그 아래로 pill(`999px`)이나 큰 반경(`8px`+)은 존재하지 않습니다 — 배지, 태그, 리액션, 버튼, 입력, 아바타 모두 같은 2px 판입니다. 완전한 원은 의미가 원일 때만 쓰입니다: 프레즌스 점, 앱 패널의 6px 상태 점, 업로드 스피너.

아바타는 원이 아니라 정사각 판입니다. 램프의 네 틴트 중 하나를 배경으로, 이니셜(한글은 한 자, 라틴은 두 자)을 `--ink-secondary` 로 얹고, 아주 옅은 안쪽 선(`inset 0 0 0 1px rgba(22,23,26,0.06)`)으로 바탕에서 떼어냅니다. 쓰이는 크기는 20px(채널 행·팔레트)과 28px(전사록 거터·사인인 푸터) 두 단계입니다.

아이콘은 직접 그린 세트입니다: 16 단위 그리드, 1.5 스트로크, round cap/join, `fill: none`, `stroke: currentColor`. 따라서 아이콘은 자기가 앉은 행의 잉크를 그대로 물려받고, 세트 전체가 한 손으로 읽힙니다. 이모지는 아이콘이 아닙니다 — 자기 색과 자기 무게를 갖고 오므로 팔레트 누수입니다. 사람이 고른 리액션 이모지만은 콘텐츠이므로 자기 글리프를 유지합니다.

채널 앞의 `#` 는 아이콘이 아니라 문자입니다. 라벨과 같은 흐름으로 조판되며, 비공개 채널만 이 크기에서 올바르게 읽히는 문자가 없어 그려진 잠금 아이콘을 씁니다.

### Named Rules

**The Two Millimetre Rule.** 반경은 `--r`(2px) 하나뿐입니다. 새 반경 값을 도입하지 말고, 원은 의미가 원(점·링)일 때만 쓰십시오.

**The Drawn Icon Rule.** 아이콘은 16 그리드·1.5 스트로크·`currentColor` 로 직접 그립니다. 아이콘 폰트, 글리프/이모지 대용, 채색된 아이콘 팩을 들이지 마십시오.

## Components

### Buttons
- **Shape:** 모든 버튼이 같은 2px 판(`--r`). pill 없음.
- **Primary:** `--signal` 바탕에 `--ink-inverse` 글자, 600/12px. 컴포저의 보내기(`0 10px` 패딩, 26px), 사인인 제출(42px 전폭), 미니앱 설치(`4px 10px`). 화면당 하나가 원칙입니다.
- **Hover / Disabled:** hover 는 `--signal-press`; disabled 는 `--n4` 바탕 + `--ink-muted` 글자로 색을 완전히 내려놓습니다.
- **Icon button:** 26×26 그리드(패널 헤더 24×24), 기본 `--ink-muted`, hover 에서 `--ink` + `--hover` 바탕. 테두리 없음.
- **Ghost / text:** 메시지 액션은 투명 1px 테두리로 자리를 잡아두고 hover 에서만 `--rule-strong` 테두리가 나타납니다 — 나타날 때 아무것도 밀리지 않습니다.
- **Focus:** `:focus-visible` 에서 `2px solid var(--signal)` 링(offset 1px). 마우스 클릭은 링을 만들지 않지만, 입력칸은 예외로 클릭 시에도 `outline-offset: -2px` 링을 그립니다.

### Chips
- **Count badge:** `--n5` 바탕, `--ink-secondary`, 600/10px, `min-width: 17px` — 숫자가 바뀌어도 칸이 유지됩니다.
- **Mention badge:** 같은 형태에 `--signal` 바탕 + `--ink-inverse`. 색을 얻는 유일한 배지입니다.
- **Tag (BOT / PIN):** 바탕 없이 `--rule-strong` 1px 테두리, `--ink-muted`, 10px 대문자 `0.05em`.
- **Reaction / attachment:** `--paper` 바탕 + `--rule` 테두리, hover 에서 `--rule-strong`. "내가 누른" 리액션은 두 번째 색이 아니라 굵기와 `--ink` 테두리로 표시합니다.
- **Scope list:** 권한은 장식된 칩의 행렬이 아니라 문장의 목록으로 읽히게 `--n2` 바탕 + `--rule` 테두리, 11px.

### Cards / Containers
카드는 없습니다. 컨테이너는 罫線으로 구획된 영역이며, 바탕은 `--board`(도크·레일) 또는 `--field`(본문·시트)이고 모서리는 각집니다. 유일하게 상자로 서는 것은 커맨드 팔레트/모달(`min(620px, 92vw)`, `max-height: 72vh`, `--paper` 바탕, `--rule-strong` 1px 테두리, floating-sheet 그림자, 반경 0)입니다.

### Inputs / Fields
- **Style:** `--paper` 바탕 + `--rule-strong` 1px 테두리 + 2px 반경. 컴포저는 `6px 6px 6px 10px` 패딩, 사인인 입력은 42px 높이의 `88px minmax(0,1fr)` 라벨 그리드 안에 채워진 셀로 앉습니다.
- **Focus:** 테두리가 `--ink` 로 올라가고 `--signal` 링이 안쪽으로 그려집니다. 캐럿도 `--signal` 입니다.
- **Disabled:** `--n2` 바탕 + `--rule` 테두리 — 조작 경계가 장식 경계로 내려앉는 것이 곧 "지금은 안 됩니다"입니다.
- **Placeholder:** `--ink-muted`.
- **Palette input:** 테두리 없이 아래 罫線 한 줄, 15px, 46px 높이.

### Navigation
- **Dock (52px):** `--board` 바탕에 34px 타일이 6px 간격으로 섭니다. hover 는 `--hover`; 현재 위치는 타일이 `--paper` 로 올라서고 `--rule-strong` 안쪽 선을 얻은 뒤, 아래 14×2px `--signal` 밑줄이 붙습니다. 배지는 `--board` 색 1px 테두리를 둘러 타일에서 떨어져 읽힙니다. 구분선은 20×1px `--rule`.
- **Channel board (260px):** 섹션 머리가 열 이름 행을 겸합니다(10px 대문자 섹션명 + 9px `--n7` 필드명 `안 읽음` + 추가 컨트롤). 행은 26px 4트랙. 평상은 `--ink-secondary`, 음소거는 `--ink-muted`, 안 읽음은 600/`--ink`, 선택은 `--paper` + 안쪽 `--rule-strong` 선 + `#`/잠금 표식만 `--signal`. 세로 강조 바를 쓰지 않습니다 — 위치는 표식이 말합니다. 수치 칸은 46px 고정 트랙의 오른쪽에 붙는 mono 배지(`min-width: 18px`)이고, 값이 바뀔 때 `flap-tick` 으로 한 번 넘어갑니다.
- **≤720px:** 보드가 가로 스트립이 되고 각 행이 `--paper` 바탕 + `--rule` 안쪽 선의 독립 판으로 서며 라벨은 `12ch` 로 제한됩니다. 열 이름 행은 이 구간에서 숨고 `--rail-tail` 은 `0px` 로 접힙니다 — 가로로 서면 열이 아니라 카드열이므로 이름표가 가리킬 열이 없습니다.

### Transcript rows
40px 거터 + 본문 2트랙. 작성자·시각은 baseline 정렬, 시각과 액션은 hover 에서 `opacity` 로만 나타나 레이아웃을 밀지 않습니다. 전사록은 `justify-content: flex-end` 로 아래에 정착합니다 — 조용한 채널의 메시지 두 개가 700px 빈 판 위에 남으면 조용한 게 아니라 고장 난 것으로 읽힙니다. 날짜 구분선은 좌측 라벨 + 남는 폭을 채우는 1px 선입니다. 나를 향한 메시지는 `--signal-wash` 바탕과 왼쪽 `inset 1px` 시그널 선을 함께 갖습니다.

### Presence
`--ink` 로 채운 8px 점 = 활성, 바탕색으로 비우고 `--ink-secondary` 1.5px 링 = 자리 비움, 가로줄로 막힌 점 = 방해 금지. 테두리 색은 앉은 바탕(`--field` 또는 `--board`)을 따릅니다.

### App panel (mini-app guest)
미니앱 패널은 `--paper` 바탕의 `iframe` 이고, 헤더의 상태 점은 앱이 신고한 `accent_color` 를 무시한 `--ink-muted` 6px 원입니다. 패널 **안쪽**은 게스트의 자기 오리진이므로 자기 스타일시트를 그대로 유지합니다 — 호스트 토큰을 주입하지 않습니다. 다만 번들된 레퍼런스 앱(`examples/apps/standup/index.html`)은 앱 작성자가 복사해 가는 출발점이므로 하우스 팔레트와 기하에서 시작합니다: `--bg #fafaf9`, `--fg #16171a`, `--muted #6a6a64`, `--border #c2c2bc`, `--accent #a50034`, `--input-bg #ffffff`, `color-scheme: light`, 반경 2px, 다크 블록 없음(호스트가 light only 이므로). 이는 게스트에 강제되는 규칙이 아니라 레퍼런스가 지켜야 할 경계입니다.

### Docked sheet (signature)
스레드와 앱 패널은 왼쪽 1px 罫線, `--field` 바탕, `--header-h` 헤더를 가진 열입니다. 등장은 `clip-path: inset(0 0 0 100%)` → `inset(0 0 0 0)` 을 `200ms cubic-bezier(0.16, 1, 0.3, 1)` 로 여는 `dock-in` 하나입니다. 시트는 자기 폭만큼 전사록을 좁히며, 전사록의 스크롤 위치는 유지됩니다.

### Notices (bottom-right stack)
우하단에 최대 3개까지 쌓이는 토스트. `320px` 폭(`max-width: calc(100vw - 28px)`), 8px 간격, `position: fixed; right: 14px; z-index: 50`, 하단은 측정값(위 The Measured Bottom Rule). 판은 `--paper` 바탕 + `--rule-strong` 1px 테두리 + 2px 반경 + notice-float 그림자입니다. 제목은 12px/600(`-0.008em`, 한 줄 줄임표), 본문은 12px/1.45 `--ink-secondary` 에 두 줄 클램프 — 토스트는 메시지를 재현하지 않고 가리킵니다. 카드 전체(`.notice-open`)가 열기 대상이고 hover 는 `--hover` 한 값, 오른쪽 26px 칸에 닫기 아이콘 버튼이 상단 정렬로 앉습니다. 멘션과 DM 만 왼쪽 1px 시그널 선(`inset 2px 0 0 -1px var(--signal)`)을 얻고, 일반 채널 알림은 무채색으로 남습니다. 등장은 `notice-in`(180ms, opacity + 6px 상승) 하나입니다.

억제 규칙도 시각 시스템의 일부입니다: 지금 화면에 있는 채널은 토스트하지 않고(보이는 메시지는 알릴 필요가 없습니다), 채널을 열면 그 채널의 대기 중 토스트가 사라집니다. 자동 소멸은 5초이며 포인터가 스택 위에 있는 동안에는 보이는 모든 토스트가 함께 멈춥니다 — 두 번째를 읽다가 세 번째를 잃지 않게 하기 위함입니다. 역할은 `role="status"` 이고 `alert` 를 쓰지 않습니다(메시지 도착은 낭독을 끊을 만한 사건이 아닙니다).

### Named Rules

**The Three Authored Motions Rule.** authored 모션은 셋이고, 공통 허가 조건은 하나입니다 — **모션은 도착을 알린다**. `dock-in`(200ms): 시트가 일 옆에 도착합니다. `notice-in`(180ms): 토스트가 일 옆에 도착합니다. `flap-tick`(160ms): 수치가 보드에 도착합니다. 도착이 아닌 것(hover, 선택, 열림/닫힘, 색 전환)은 즉시 일어납니다. 그 밖의 애니메이션은 진행을 알리는 두 개(부팅 스윕, 업로드 스피너)뿐입니다. `prefers-reduced-motion: reduce` 에서 모든 지속시간이 1ms 로 내려가되(플랩은 0.001s) 두 진행 표시만 계속 돕니다.

**The Flap Belongs To The Count Rule.** 안내판이 변화를 알리는 방식은 칸을 넘기는 것이고, 표면에서 그 기계 장치를 쓸 자격이 있는 것은 단 하나 — 스스로 바뀌는 유일한 칸, 즉 수치 필드입니다. `flap-tick` 은 `.badge` 에만, 한 번만, 값이 실제로 바뀔 때만 돕니다(컴포넌트가 배지를 자기 값으로 키잉해 리마운트하므로 무관한 리렌더에서는 돌지 않습니다). 다른 칸에 플랩을 확장하지 마십시오 — 값이 스스로 변하지 않는 칸이 넘어가면 그것은 장식입니다.

**The State Is Also Form Rule.** 어떤 상태도 색만으로 말하지 않습니다. 시그널이 등장할 때는 항상 굵기·형태·罫線 중 하나가 동반됩니다(멘션 행의 inset 선, 오류 배너의 inset 선, 활성 도크 타일의 판 상승).

## Do's and Don'ts

### Do:
- **Do** 모든 톤을 `--n0`…`--n10` 에서 고르십시오. 램프 밖의 회색은 버그입니다.
- **Do** 바탕을 역할대로 쓰십시오: `--board` 는 무광 판(도크·레일), `--field` 는 읽는 판(전사록·시트), `--paper` 는 입력 가능하거나 선택된 것.
- **Do** 罫線을 역할대로 나누십시오: 영역 분할은 `--rule`, 조작·상태 경계는 `--rule-strong`.
- **Do** 안 읽음은 `font-weight: 600` 과 `--ink` 로 표현하십시오.
- **Do** 열 폭을 토큰으로 고정하고 행만 변하게 하십시오(`--dock-w` 52px, `--rail-w` 260px, `--thread-w`, `--panel-w`).
- **Do** 숫자가 들어가는 자리에 `min-width` 를 주어 값이 바뀌어도 행이 밀리지 않게 하십시오.
- **Do** 열에 이름을 붙일 때는 그 트랙을 먼저 고정 폭 토큰으로 만드십시오(`--count-w`). 이름표 우변과 값 우변이 같은 px 인지로 검사하십시오.
- **Do** 세는 숫자는 `--font-mono` + `tabular-nums` 로 조판하십시오.
- **Do** 새 아이콘은 16 그리드·1.5 스트로크·`currentColor` 로 직접 그리십시오.
- **Do** 상태를 색과 형태로 이중 인코딩하십시오(색맹 사용자에게도 살아남아야 합니다).
- **Do** 가장 작은 글자에 `--ink-muted` 를 쓰십시오. 이보다 옅은 잉크 단계는 시스템에 없습니다.
- **Do** 하단 모서리에 붙는 floater 의 `bottom` 을 컴포저 실측값으로 계산하십시오. 고정 오프셋은 컴포저가 자라면 보내기 버튼을 덮습니다.
- **Do** 알림처럼 임시로 뜨는 표면에서도 "나를 향한 것"은 전사록과 같은 왼쪽 1px 시그널 선으로 표시하십시오.
- **Do** 좁아질 때 숨기는 대신 스택하거나 축을 바꾸십시오.
- **Do** 다크 테마가 필요해지면 램프만 반전시키십시오. 컴포넌트 규칙은 손대지 않고 성립하도록 authored 되어 있습니다.

### Don't:
- **Don't** `--signal` 을 멘션·오류·포커스·주 동작·현재 위치 밖에서 쓰지 마십시오. 두 번째 유채색을 추가하지 마십시오.
- **Don't** 아바타·태그·프레즌스·앱 아이콘에 색상환을 도입하지 마십시오. 미니앱의 `accent_color` 도 존중하지 않습니다.
- **Don't** 카드, 둥근 패널, 상시 그림자, 쌓인 컨테이너를 만들지 마십시오. 구획은 1px 선입니다.
- **Don't** `--r`(2px) 밖의 모서리 반경을 도입하지 마십시오. pill 은 이 표면에 없습니다.
- **Don't** 진짜로 떠 있지 않은 것에 그림자를 주지 마십시오. 하드 오프셋 그림자, 헤일로, 컬러 글로우는 금지입니다.
- **Don't** hover 나 상태 전환에서 레이아웃을 밀지 마십시오. `opacity` 와 투명 테두리 예약으로 처리하십시오.
- **Don't** 두 번째 서체나 새 글자 크기를 들이지 마십시오. 21/15/14/13/12/11/10px 밖의 값을 쓰지 마십시오.
- **Don't** 10px 대문자 트래킹 라벨을 그 한 단계 밖으로 확장하지 마십시오(작은 대문자 눈썹/키커를 새로 만들지 마십시오).
- **Don't** 아이콘 자리에 이모지를 대신 놓지 마십시오. 사람이 고른 리액션 이모지만 콘텐츠로 남습니다.
- **Don't** 지금 화면에 있는 채널을 토스트하지 마십시오. 보이는 메시지를 알리는 것은 소음입니다.
- **Don't** 토스트에 메시지 본문을 다 담지 마십시오(두 줄 클램프). 토스트는 포인터입니다.
- **Don't** 스레드나 패널을 전사록 위에 덮지 마십시오(≤720px 의 강제 스택만 예외).
- **Don't** `dock-in`·`notice-in`·`flap-tick` 외에 새 애니메이션을 authored 하지 마십시오. 새 모션은 "도착을 알리는가"라는 조건을 통과해야 합니다.
- **Don't** `flap-tick` 을 수치 칸 밖으로 확장하지 마십시오. 스스로 바뀌지 않는 칸이 넘어가면 장식입니다.
- **Don't** `auto` 트랙 위에 열 이름을 붙이지 마십시오. 머리 행과 데이터 행은 별개의 그리드이므로 정렬이 성립하지 않습니다.
- **Don't** 미니앱 패널 안쪽에 호스트 토큰을 주입하지 마십시오. 게스트는 자기 오리진의 스타일을 유지하고, 하우스 스타일은 레퍼런스 앱으로 전파합니다.
- **Don't** 좁은 폭에서 사용자가 방금 연 시트를 조용히 제거하지 마십시오.
