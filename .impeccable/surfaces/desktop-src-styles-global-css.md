---
version: 1
slug: "desktop-src-styles-global-css"
primary_target: "desktop/src/styles/global.css"
related_targets: ["desktop/src/app/App.tsx","desktop/src/components"]
---

스코프: Llack 앱 셸 전체 (도크 · 사이드바 · 채널 헤더 · 전사록 · 컴포저 · 스레드 · 앱 패널 · 에이전트 패널 · ⌘K 팔레트 · 새 대화 · 로그인). 방문자 모드: Operate.

대상: 사내 팀 구성원. 하루 8시간 창을 켜둔 채 훑고, 스레드에서 결론을 내고, 미니앱과 에이전트를 실행합니다. 고정 조건: 이름 Llack · 한국어 존댓말 · LG Red `#A50034` primary · 라이트 우선.

## Direction contract

THESIS: 카드는 시트다. 도킹되는 판 하나하나가 손에 쥐는 표이고, 그 안의 전사록은 읽는 면이라 판이 되지 않는다. 각진 판과 罫線만의 구획을 거부한다 — 열 고정 논리는 그대로 살아남는다.

OWN-WORLD: 승차권 카드 스톡. 옅은 회색(hue 336, 채도 2% 미만) 바탕 위에 흰 판이 반경 16px 다이컷 모서리로 떠오르고, 깊이는 밀착 그림자 하나(`--contact`)와 두 겹 부드러운 그림자 셋(`--e-2`…`--e-4`)이며 항상 헤어라인을 동반한다. 반경 다섯 단계는 전부 동심 규칙(`안쪽 = 바깥쪽 − 안여백`)에서 파생된다. 칩과 입력은 반대로 파인다. 인쇄 강조색은 LG Red 하나. 단일 서체 Pretendard, 여섯 단계 스케일, 세는 숫자는 mono + tabular. 좌측 레일은 밝게 유지한다.

STORY: 훑는다 → 내 것과 안 읽은 곳을 즉시 분간한다 → 스레드로 들어가도 채널을 잃지 않는다 → 표면이 종일 조용하다.

FIRST VIEWPORT: 좌 56px 도크(둥근 타일) · 264px 채널 레일(32px 행, 선택 행이 흰 카드로 떠오름) · 흰 전사록 카드. 채널 헤더는 전사록 카드 안에 있고 시트마다 자기 헤더를 갖는다. 컴포저는 반경 16px 카드로 하단에 떠 있고 화면을 종결한다. 시그니처: 시트가 음수 margin 으로 폭을 되돌려주며 전사록을 실제로 밀어낸다(220ms).

FORM: 승차권·개찰 카드(역 세계 — 안내판의 형제). 자체 후보 목록 3순위. seed b60db9df.

AMEND — 전사록은 판이 되지 않는다: 초안 THESIS 는 "행은 카드다" 였고 마감 리뷰가 그 약속대로 메시지 행에 카드를 요구했다. 거부한다. 8시간 훑는 전사록에서 메시지마다 판을 두르면 스캔 비용이 오르고, 이 제품의 1순위 원칙("훑기가 최우선")과 정면으로 충돌한다. 카드가 되는 것은 시트·레일 행·나를 향한 메시지 셋뿐이고, 그것이 카드일 자격은 "옆에 도착한 물건"이기 때문이다. 평범한 메시지는 hover 에서만 판이 된다.

RAISE (j-card): 모든 칸이 용량을 선언하고 내용은 거기에 맞춰 잘린다.
RAISE (starship): 이름 없는 영역과 이름 없는 상태를 두지 않는다.
RAISE (Miura): 하나의 반경 규칙이 전 컴포넌트에 전파된다. 국소 예외 금지.
RAISE (HyperCard): 읽는 자리에서 고친다. 고칠 수 있는 것에 모달을 쓰지 않는다.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## 미결

- 다크 테마: 램프가 반전 가능하게 authored 되지만 이번 범위 아님.
- 채널 멤버 목록: 백엔드에 채널별 멤버 엔드포인트가 없어 헤더의 인원수가 아직 비활성.
- 이모지 피커·채널 섹션 편집 UI: 제품 기능 미구현.
