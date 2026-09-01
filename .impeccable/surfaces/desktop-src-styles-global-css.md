---
version: 1
slug: "desktop-src-styles-global-css"
primary_target: "desktop/src/styles/global.css"
related_targets: ["desktop/src/app/App.tsx","desktop/src/components"]
---

스코프: Llack 앱 셸 전체 (도크 · 사이드바 · 채널 헤더 · 전사록 · 컴포저 · 스레드 · 앱 패널 · ⌘K 팔레트 · 로그인). 방문자 모드: Operate.

대상: 사내 팀 구성원. 하루 8시간 창을 켜둔 채 훑고, 스레드에서 결론을 내고, 미니앱을 실행합니다. 고정 조건: 이름 Llack · 한국어 존댓말 · LG Red `#A50034` primary · 라이트 우선(다크는 추후).

## Direction contract

THESIS: 채널 목록은 출발 안내판이다. 열은 고정, 행만 살아 움직인다. 좌측 다크 레일과 카드 쌓기를 거부한다.

OWN-WORLD: 무광 안내판 바탕 `#F7F7F5`, 잉크 `#16171A`, 11단 무채색 램프가 유일한 톤 토큰, 1px 罫線이 유일한 구획 수단. 카드·그림자·둥근 패널 금지. LG Red는 "나를 향한 것"(멘션·안 읽음·현재 위치) 단 하나의 의미로만 등장. 단일 서체, tabular 숫자.

STORY: 훑는다 → 내 것을 즉시 분간한다 → 스레드로 들어가도 채널을 잃지 않는다.

FIRST VIEWPORT: 좌 56px 도크(아이콘) · 264px 채널 보드(고정 필드 [상태][구분][이름][수치]) · 전사록. 헤더는 罫線 한 줄로만 분리. 컴포저 하단 고정. 시그니처: 스레드가 덮지 않고 옆으로 밀어 열린다.

FORM: 안내판(역·공항 시각표). 자체 후보 목록 3순위. seed 00fca558.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## 미결

- 다크 테마: 토큰 구조는 견디게 잡되 이번 범위 아님.
- 이모지 피커·채널 섹션 편집 UI: 제품 기능 미구현이라 화면 없음.
