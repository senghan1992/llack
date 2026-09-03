# 미니앱 플랫폼

팀이 만든 도구를 Llack 안에 붙이는 방법. 이 플랫폼의 목표는 하나입니다:

> **사내 도구 하나 붙이는 비용을 "정적 HTML 한 장 + 매니페스트 한 장"으로 낮춘다.**

API 키 발급, OAuth 왕복, 앱 전용 DB, 백엔드 배포 — 전부 없앴습니다.

---

## 개념

**App** 은 등록된 소프트웨어입니다. **AppInstallation** 은 그것을 특정 워크스페이스에
설치한 결과이며, 실제로 권한을 부여하고 설정과 저장소를 갖는 주체입니다.

둘을 나눈 이유: 같은 사내 도구(예: "배포 현황")를 한 번 만들어 여러 워크스페이스에
설치하고, 각각 다른 설정과 다른 권한 범위를 갖게 하려면 이 분리가 필요합니다.

```
App (slug: deploy-status)
 ├── AppInstallation (워크스페이스 A) — scopes: [channels:read, messages:write]
 │     ├── 봇 사용자 "배포 현황"
 │     ├── config: { project: "web" }
 │     └── storage: 이 설치만의 KV
 └── AppInstallation (워크스페이스 B) — scopes: [messages:write]
       └── …
```

## 표면

앱은 세 가지 방식으로 존재할 수 있습니다.

| 종류 | `kind` | 설명 |
| --- | --- | --- |
| 패널 | `panel` | 좌측 독에서 열리는 UI. 채널 옆 분할 패널로 뜹니다. |
| 봇 | `bot` | UI 없이 메시지만 올립니다. CI 알림 같은 용도. |
| 둘 다 | `both` | 패널 UI + 봇 계정. |

## 매니페스트

앱 등록에 필요한 전부입니다.

```json
{
  "slug": "standup",
  "name": "데일리 스탠드업",
  "version": "0.1.0",
  "tagline": "매일 아침 팀의 진행 상황을 모아 채널에 올립니다",
  "kind": "both",
  "panel_url": "https://apps.example.com/standup/",
  "home_url": "https://apps.example.com/standup/home",
  "command_url": "https://apps.example.com/standup/llack/command",
  "interaction_url": "https://apps.example.com/standup/llack/interact",
  "event_webhook_url": "https://apps.example.com/standup/llack/events",
  "default_width": 420,
  "accent_color": "#7c6aff",
  "scopes": ["identity:read", "channels:read", "messages:write", "storage", "panel:ui"],
  "slash_commands": [{ "command": "/standup", "description": "스탠드업 작성", "usage": "/standup [팀]" }],
  "events": ["message.created", "app.mention"]
}
```

| 필드 | 뜻 |
| --- | --- |
| `panel_url` | 채널 옆 패널(사이드 시트)에 뜨는 화면 |
| `home_url` | 채널과 무관한 앱 전용 화면 — 메인 패널의 **앱 홈** (`POST /app-installations/{id}/home-session`) |
| `command_url` | 사람이 `/standup …` 을 치면 서명된 POST 가 오는 곳 |
| `interaction_url` | 앱 메시지 안의 버튼·선택을 누르면 서명된 POST 가 오는 곳 |
| `event_webhook_url` + `events` | 구독한 이벤트가 서명된 POST 로 오는 곳 |

등록은 환경설정 → **개발자 콘솔**에 JSON 을 붙이거나 API 로:

```bash
curl -X POST "$API/apps?workspace_id=$WORKSPACE_ID" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d @manifest.json
# → {..., "secret": "llack_as_..."}  ← 서명 비밀. 이 응답에서만 보입니다.
```

### 상태와 심사

| 상태 | 뜻 |
| --- | --- |
| `draft` | 만든 워크스페이스의 디렉터리에만 보이고 그곳에서만 설치됩니다 — 팀이 자기 앱을 쓰는 데는 이걸로 충분합니다 |
| `pending_review` | `POST /apps/{id}/submit` — 모든 워크스페이스에 내놓겠다고 신청한 상태 |
| `published` | 서비스 관리자가 `POST /apps/{id}/review {"decision":"approve"}` — 모든 디렉터리에 보이고 어디서나 설치됩니다 |
| `rejected` | 반려. `review_note` 에 이유. 고쳐서 다시 신청할 수 있습니다 |
| `disabled` | 작성자가 잠시 내림 (`PUT /apps/{id}/status`) |

작성자는 `published` 를 직접 쓸 수 없습니다(403 `review_required`). 심사 대기 목록은
`GET /apps/pending`(서비스 관리자). 결정은 작성자에게 `notification` 프레임(`kind: "review"`)으로
가고 감사 로그에 `app.review_decided` 로 남습니다.

## 스코프

| 스코프 | 허용하는 것 |
| --- | --- |
| `identity:read` | 앱 자신의 컨텍스트와 실행 중인 사용자 확인 |
| `channels:read` | 채널 목록 (DM 은 **절대** 포함되지 않음) |
| `messages:read` | 메시지 읽기 |
| `messages:write` | 봇 계정으로 메시지 게시 |
| `files:read` / `files:write` | 파일 읽기 / 올리기 |
| `users:read` | 구성원 목록 |
| `notify` | 특정 사용자에게 데스크톱 알림 |
| `storage` | 설치 단위 KV 저장소 |
| `panel:ui` | 패널 제목 변경, 채널 이동, 패널 닫기 |

설치 화면에서 각 스코프가 한국어 설명으로 표시됩니다
(`desktop/src/components/AppDock.tsx:describeScope`).

## 보안 모델

네 가지 규칙이 전부입니다. 각각이 막는 것을 함께 적었습니다.

### 1. 패널은 사용자 토큰을 절대 못 받는다

호스트가 **설치 단위로 스코프가 제한된 단기 토큰**(bridge token, 기본 10분)을 만들어
`postMessage` 로 프레임에 넘깁니다. 이 토큰으로 열리는 것은 `/app-bridge/*` 뿐입니다.

종단 검증으로 확인한 항목: 브릿지 토큰으로 `GET /workspaces` 와
`GET /auth/sessions` 를 시도하면 실패합니다.

### 2. 권한의 기준은 토큰이 아니라 설치 레코드

브릿지 요청마다 `app_installations.granted_scopes` 를 다시 봅니다.
따라서 관리자가 권한을 좁히면 **이미 발급된 토큰에도 즉시 적용**됩니다.
토큰이 만료될 때까지 기다리지 않습니다.

### 3. 매니페스트가 요청하지 않은 스코프는 부여할 수 없다

설치 시 스코프를 **좁힐 수는 있지만 넓힐 수는 없습니다**.
매니페스트에 없는 스코프를 주려 하면 `scope_not_requested` 로 거부됩니다.

### 4. iframe 은 `allow-same-origin` 없이 샌드박스

```html
<iframe sandbox="allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox">
```

`allow-same-origin` 이 **의도적으로 빠져 있습니다**. 있으면 프레임이 호스트와 오리진을
공유해 호스트의 storage 를 읽을 수 있습니다. 없으면 프레임은 완전히 격리되고,
postMessage 브릿지로만 호스트에 닿습니다.

호스트로 들어오는 모든 메시지는 앱의 `panel_url` 오리진과 대조합니다.
다른 곳에서 온 메시지는 버립니다. 호스트가 응답을 보낼 때도 `"*"` 가 아니라
그 오리진을 지정합니다 — 와일드카드는 프레임에 무엇이 로드되어 있든 브릿지 토큰을
넘겨주게 됩니다 (`desktop/src/components/AppPanel.tsx`).

### 그리고: DM 은 스코프가 아니라 하드 경계

`channels:read` 를 줘도 앱은 DM 을 보지 못합니다. 스코프로 조절하는 값이 아니라
쿼리 수준에서 배제됩니다 (`api/v1/apps.py:bridge_list_channels`).

### 봇 계정

메시지를 올리는 앱은 설치할 때 **자기 봇 사용자**를 받습니다. 대화 기록에서
작성자가 모호해지는 일이 없고, 앱을 제거해도 봇 사용자는 남습니다 —
과거 메시지가 이름과 아바타를 잃지 않게 하기 위해서입니다.

---

## SDK

```bash
npm install @llack/app-sdk   # 사내 레지스트리 또는 로컬 경로
```

```ts
import { createClient, LlackError } from "@llack/app-sdk";

const llack = await createClient();

// 어디서 실행 중인지
const { workspace_id, channel_id, user } = llack.context;

// 설치 시 관리자가 넣은 설정
const project = llack.config.project;

// 권한은 미리 확인할 수 있습니다
if (llack.hasScope("messages:write")) {
  await llack.messages.post({
    channelId: channel_id!,
    body: "배포가 완료되었습니다 ✅",
    // 멱등키: 재시도가 중복 게시가 되지 않습니다
    clientMsgId: `deploy-${releaseId}`,
  });
}

// 앱 전용 저장소 — 자체 DB 가 필요 없는 이유
await llack.storage.set("last-run", { at: Date.now() });                    // 공용
await llack.storage.set("draft", draft, { user: user.id });                 // 사용자별
const settings = await llack.storage.get("settings");                       // 없으면 null

// 패널 UI 제어
llack.ui.setTitle("배포 현황 · web");
llack.ui.openChannel(someChannelId);

// 오류는 코드로 분기합니다
try {
  await llack.channels.list();
} catch (error) {
  if (error instanceof LlackError && error.isMissingScope) {
    // 관리자에게 권한 요청 안내
  }
}
```

브릿지 토큰이 만료되면 SDK 가 호스트에서 새 세션을 받아 **한 번 자동 재시도**합니다.
앱 코드가 만료를 다룰 필요가 없습니다.

## 서버 대 서버

패널 없이 CI 등에서 메시지를 올리려면 장기 토큰을 발급합니다. 개발자 콘솔의 "토큰 발급"이
아래를 호출합니다 — 토큰은 앱의 홈 워크스페이스 설치본(봇 계정)에 묶입니다.

```bash
curl -X POST "$API/apps/$APP_ID/tokens" \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"name": "github-actions", "expires_in_days": 365}'
# → {"token": "llack_at_...", "token_prefix": "llack_at_ab12", ...}  ← 이때 한 번만
curl "$API/apps/$APP_ID/tokens"                       # 목록 (평문 없음)
curl -X DELETE "$API/apps/$APP_ID/tokens/$TOKEN_ID"   # 폐기
```

```bash
curl -X POST "$API/channels/$CHANNEL_ID/messages" \
  -H "Authorization: Bearer llack_at_..." -H "Content-Type: application/json" \
  -d '{"body": "빌드 #482 통과 ✅", "client_msg_id": "build-482",
       "blocks": [{"type": "actions", "elements": [
         {"type": "button", "text": "배포", "action_id": "deploy", "style": "primary"}]}]}'
```

토큰은 해시로만 저장되고 `token_prefix` 만 UI 에 표시됩니다. 설치본 단위 발급
(`POST /app-installations/{id}/tokens`)도 그대로 있습니다.

## 서명 — Llack 이 앱을 부를 때

명령·인터랙션·이벤트 웹훅은 모두 같은 방식으로 서명됩니다.

```
X-Llack-Timestamp: 1788400000
X-Llack-Signature: sha256=HMAC_SHA256(app_secret, f"{timestamp}.{body}")
```

`body` 는 받은 바이트 그대로(정렬된 키, 공백 없는 JSON). 앱은 같은 HMAC 을 계산해 비교하고,
타임스탬프가 5분 이상 오래되면 거부하세요. 비밀은 등록 응답과
`POST /apps/{id}/rotate-secret` 에서만 보입니다. 타임아웃 5초, 리다이렉트 3회, 대상 주소는
공개 호스트만(사설·루프백은 링크 프로브와 같은 가드로 거부).

### 슬래시 명령

`GET /workspaces/{ws}/commands` 가 내장(`/remind`, `/dnd`, `/topic`, `/leave`, `/mute`, `/shrug`)과
설치된 앱의 명령을 합쳐 돌려줍니다. 사람이 `/standup 백엔드` 를 보내면
`POST /channels/{id}/commands {"text": "/standup 백엔드"}` → `command_url` 로:

```json
{ "command": "/standup", "text": "백엔드",
  "user": {"id","handle","display_name"}, "channel": {"id","name"},
  "workspace_id": "...", "response_url": "https://llack.example.com/api/v1/apps/APP/respond/NONCE" }
```

앱 응답 `{"text": "...", "ephemeral": true, "blocks": []}` — `ephemeral` 이면 명령한 사람에게만
보이고, 아니면 앱 봇 메시지로 게시됩니다. 30분 안에 `response_url` 로 (같은 서명으로) POST
하면 나중에 채널에 게시할 수 있습니다. 한 번만 쓸 수 있는 URL 입니다.

### 인터랙티브 블록

앱 메시지의 `blocks`:

```json
[
  {"type": "section", "text": "v2.3.0 을 프로덕션에 올릴까요?"},
  {"type": "actions", "elements": [
    {"type": "button", "text": "승인", "action_id": "approve", "value": "v2.3.0", "style": "primary"},
    {"type": "select", "action_id": "env", "placeholder": "환경", "options": [{"text": "스테이징", "value": "stg"}]}
  ]},
  {"type": "context", "text": "배포 봇 · 자동 생성"}
]
```

누르면 `POST /messages/{id}/actions {"action_id","value"}` → `interaction_url` 로
`{"type": "block_action", "action_id", "value", "user", "channel", "message_id", "message", "response_url"}`.
앱 응답 `{"replace_original": {"text","blocks"}, "ephemeral": {"text"}}` — 원문이 바뀌면
모두에게 `message.updated` 가 가고, `ephemeral` 은 누른 사람만 봅니다. 알 수 없는 블록 타입은
422 `invalid_blocks`; `unfurl` 블록은 서버만 씁니다.

### 이벤트 웹훅

`events` 에 적은 것만 옵니다: `message.created`(앱 자신의 봇 글은 제외), `reaction.added`,
`channel.member_joined`, `app.mention`(앱 봇을 멘션한 메시지). 봉투:

```json
{"type": "message.created", "delivery_id": "...", "app_id": "...", "installation_id": "...",
 "workspace_id": "...", "sent_at": "...", "data": {"message": {...}}}
```

첫 시도는 즉시, 실패하면 30초 → 2분 → 10분 뒤 재시도 후 `failed`. 전달 기록은
`GET /apps/{id}/deliveries`, 연결 확인은 `POST /apps/{id}/test-webhook`(`ping` 1건). 개발자 콘솔의
"웹훅 테스트"·"웹훅 전달 기록"이 이 둘입니다.

## 브릿지 API

`/api/v1/app-bridge/*` — 의도적으로 작게 유지한 표면입니다.

| 메서드 | 경로 | 필요 스코프 |
| --- | --- | --- |
| GET | `/context` | `identity:read` |
| GET | `/channels` | `channels:read` |
| POST | `/messages` | `messages:write` |
| POST | `/notify` | `notify` |
| GET/PUT/DELETE | `/storage/{key}` | `storage` |
| GET | `/storage` | `storage` |

## 예제 앱

[`examples/apps/standup`](../examples/apps/standup) 이 위의 모든 요소를 한 파일에 담은
참조 구현입니다. 실행 방법은 그 폴더의 README 에 있습니다.

## 앞으로

지금 초안에 아직 없는 것 — [ROADMAP.md](ROADMAP.md) 참고:

- 앱 심사 화면의 스크린샷·권한 diff 미리보기
- 웹훅 서명 검증용 SDK 헬퍼 (지금은 문서의 HMAC 식을 직접 구현)
