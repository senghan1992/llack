# 데일리 스탠드업 (예제 미니앱)

Llack 미니앱 플랫폼의 참조 구현입니다. 한 파일 안에 앱이 갖춰야 할 요소가 모두 들어 있습니다.

| 요소 | 이 예제에서의 위치 |
| --- | --- |
| 매니페스트 (권한·표면 선언) | `manifest.json` |
| 호스트 핸드셰이크 | `main.js` 의 `createClient()` |
| 설치 시 설정값 읽기 | `llack.config.channel_slug` |
| 앱 전용 저장소 | `llack.storage.get/set` (사용자 스코프) |
| 봇 계정으로 메시지 전송 | `llack.messages.post` |
| 패널 UI 제어 | `llack.ui.setTitle` |

## 실행

1. SDK 빌드:
   ```bash
   cd packages/llack-app-sdk && npm install && npm run build
   ```
2. 이 폴더를 정적 서버로 띄웁니다 (매니페스트의 `panel_url` 과 포트를 맞추세요):
   ```bash
   cd examples/apps/standup && python3 -m http.server 5180
   ```
3. 앱을 등록하고 게시합니다 (`<TOKEN>` 은 로그인 응답의 `access_token`):
   ```bash
   curl -X POST "http://localhost:8000/api/v1/apps?owner_workspace_id=<WORKSPACE_ID>" \
     -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" \
     -d @manifest.json

   curl -X PUT "http://localhost:8000/api/v1/apps/<APP_ID>/status" \
     -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" \
     -d '{"status": "published"}'
   ```
4. 데스크톱 앱의 좌측 독에서 **+** 를 눌러 설치하면, 요청한 권한 목록이 한국어로 표시됩니다.

## 왜 API 키가 없는지

패널은 샌드박스된 iframe 안에서 돌아가고, 사용자의 액세스 토큰을 절대 받지 않습니다.
호스트가 **설치 단위로 스코프가 제한된 단기 토큰**(bridge token)을 만들어 프레임에 넘겨주며,
그 토큰으로 열 수 있는 것은 `/app-bridge/*` 뿐입니다. 관리자가 설치 시 권한을 좁히면
이미 발급된 토큰에도 즉시 반영됩니다 — 권한의 기준은 토큰이 아니라 설치 레코드입니다.
