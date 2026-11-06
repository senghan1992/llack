# 배포

팀에게 "이거 쓰세요"라고 말하기 전에 읽는 문서입니다. 단일 서버, 수십 명
규모의 사내 파일럿을 기준으로 합니다.

셋 중 하나를 고르면 됩니다.

| 경로 | 언제 | 뭐가 필요 |
| --- | --- | --- |
| [A. SQLite 단일 인스턴스](#a-sqlite-단일-인스턴스) | 가장 단순하게 시작할 때 | 파이썬, 파일 하나 |
| [B. Postgres](#b-postgres) | 인스턴스를 늘리거나 백업이 필요할 때 | Postgres |
| [C. Docker Compose](#c-docker-compose) | 이미 컨테이너로 돌릴 때 | Docker, Compose |

## 먼저 준비할 것 — 서명 키

모든 토큰은 `SECRET_KEY` 로 서명됩니다. 배포 전에 반드시 새로 뽑으세요.

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

이 값을 `.env` 의 `SECRET_KEY` 에 넣습니다. 나중에 이 값을 바꾸면 발급된
토큰이 전부 무효가 되므로 — 전원을 재로그인시키게 됩니다 — 바꾸기 전에
알려두세요.

## A. SQLite 단일 인스턴스

인스턴스 하나를 돌리는 동안에는 DB 가 파일 하나입니다. `backend/llack.db` 가
그 파일이고, 백업은 파일을 복사하면 끝납니다.

```bash
# 1. 설치
cd /opt/llack
make setup-backend

# 2. 환경 변수
mkdir -p /etc/llack
cat > /etc/llack/llack.env <<'EOF'
SECRET_KEY=<위에서 뽑은 값>
DATABASE_URL=sqlite+aiosqlite:////opt/llack/backend/llack.db
UPLOAD_DIR=/var/lib/llack/uploads
CORS_ORIGINS=https://llack.example.com
EOF

# 3. 실행
cd /opt/llack/backend
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 \
    --proxy-headers --forwarded-allow-ips 127.0.0.1
```

테이블은 서버가 기동할 때 메타데이터에서 만들어집니다 — 마이그레이션 단계가
없습니다. 처음 뜬 서버가 곧 데이터베이스입니다.

### systemd

```ini
# /etc/systemd/system/llack.service
[Unit]
Description=Llack API
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=llack
Group=llack
WorkingDirectory=/opt/llack/backend
EnvironmentFile=/etc/llack/llack.env
ExecStart=/opt/llack/backend/.venv/bin/uvicorn app.main:app \
  --host 127.0.0.1 --port 8000 \
  --proxy-headers --forwarded-allow-ips 127.0.0.1
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now llack
sudo journalctl -u llack -f
```

**워커를 둘 이상 띄우지 마세요.** `backend/Dockerfile` 의 CMD 에
`--workers 4` 가 들어 있지만, 그대로 쓰면 실시간이 끊깁니다 — 허브가 프로세스
안에 있어서 메시지를 보낸 워커의 이벤트가 다른 워커에 붙은 소켓에 닿지
않습니다. 인스턴스당 프로세스 하나가 오늘의 정답입니다.

### 백업

상태는 두 가지입니다 — DB 파일과 첨부 파일 디렉터리.

```bash
sudo systemctl stop llack
cp /opt/llack/backend/llack.db /backup/llack-$(date +%F).db
sudo tar czf /backup/uploads-$(date +%F).tgz -C /var/lib/llack uploads
sudo systemctl start llack
```

## B. Postgres

인스턴스를 늘리거나, 표준 백업 도구를 쓰거나, 호스팅이 DB 를 질 수 있게
하려면 Postgres 로 바꿉니다. 코드는 같습니다 — URL 만 바뀝니다.

```bash
DATABASE_URL="postgresql+asyncpg://llack:llack@db.example.com:5432/llack"
```

개발용 Postgres 설정은 `backend/.env.postgres` 에 있습니다(저장소에서 gitignore 대상).

```bash
sudo -u postgres psql -c "CREATE ROLE llack LOGIN PASSWORD 'llack';"
sudo -u postgres psql -c "CREATE DATABASE llack OWNER llack ENCODING 'UTF8';"
```

**여전히 인스턴스당 프로세스 하나**입니다. 실시간 허브가 프로세스 안이기
때문입니다. 여러 인스턴스를 동시에 띄우려면 먼저 공유 이벤트 버스(Redis 같은
것)를 넣는 작업이 필요합니다 — 그 전까지는 한 인스턴스가 안전합니다.

백업은 `pg_dump` 에 맡깁니다.

```bash
pg_dump -Fc -U llack llack > /backup/llack-$(date +%F).dump
```

## C. Docker Compose

Postgres 와 API 두 개만 뜹니다. Redis 나 MinIO 는 없습니다 — 실시간은
프로세스 안에서 되고, 파일은 디스크에 있습니다.

```bash
cp .env.example .env
# .env 에 SECRET_KEY 를 넣습니다
docker compose up -d --build
docker compose logs -f api
```

- API: http://localhost:8000
- Postgres: localhost:5432 (llack / llack / llack)

상태는 두 개의 볼륨에 있습니다 — `postgres-data`(DB)와 `api-var`(첨부 파일).
백업은 이 둘을 담으면 됩니다.

```bash
docker compose down          # 컨테이너만 내립니다
docker compose down -v       # 볼륨까지 지웁니다 (데이터가 사라집니다)
```

compose 의 API 컨테이너는 워커 하나로 뜹니다. 이유는 A 절에 적힌 것과
같습니다 — 실시간 허브가 프로세스 안입니다.

## 환경 변수

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `SECRET_KEY` | 개발용 기본값 | 모든 토큰의 서명 키. 배포 전 반드시 변경 |
| `DATABASE_URL` | `sqlite+aiosqlite:///./llack.db` | `postgresql+asyncpg://…` 로 바꾸면 Postgres |
| `UPLOAD_DIR` | `backend/var/uploads` | 첨부 파일이 저장되는 디렉터리 |
| `CORS_ORIGINS` | `*` | 허용할 오리진(쉼표 구분) |
| `ACCESS_TOKEN_TTL_SECONDS` | `1800` | 액세스 토큰 수명 (30분) |
| `REFRESH_TOKEN_TTL_SECONDS` | `2592000` | 리프레시 토큰 수명 (30일) |
| `JWT_ALGORITHM` | `HS256` | JWT 서명 알고리즘 |
| `MAX_UPLOAD_BYTES` | `20971520` | 첨부 파일 최대 크기 (20MiB) |

`SECRET_KEY` · `DATABASE_URL` · `UPLOAD_DIR` 는 `LLACK_` 붙은 이름으로도
읽힙니다(`LLACK_SECRET_KEY` 등). 같은 값을 두 이름으로 주지 마세요 — 어느
쪽이 쓰였는지 헷갈립니다.

`.env` 는 어디서 읽히나:

- `docker compose` — 프로젝트 루트의 `.env`
- 백엔드를 직접 띄울 때 — `backend/.env` (`backend/app/core/config.py` 의
  `env_file` 설정)

## 리버스 프록시

API 는 리버스 프록시 뒤에 두는 것을 권합니다. 예시는 `deploy/nginx.conf`
에 있습니다 — `/api/` 와 `/api/v1/ws` 를 API 로 넘기고, WebSocket 업그레이드
헤더와 긴 읽기 타임아웃을 붙입니다.

```nginx
location /api/v1/ws {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_read_timeout 3600s;
}
```

**WebSocket 은 프록시를 지나야 같은 오리진이 됩니다.** 웹뷰에서
`wss://llack.example.com/api/v1/ws?token=…` 로 붙는 경로이므로, 프록시가
업그레이드를 그대로 통과시키지 않으면 소켓이 열리지 않습니다.

**CORS_ORIGINS** 는 브라우저로 여는 경우에 필요한 값입니다. 데스크톱 앱은
플랫폼마다 정해진 파일 프로토콜 오리진(`tauri://localhost` 또는
`http://tauri.localhost`)으로 접속하므로 `*` 로 두어도 동작합니다. 좁히려면
그 오리진과, 브라우저로 여는 주소까지 나열하세요.

```bash
CORS_ORIGINS=https://llack.example.com
```

**한 가지 주의**: WebSocket 인증 토큰이 쿼리 문자열에 실립니다
(`?token=…`). 프록시 access log 를 그대로 남기면 토큰이 로그에 들어갑니다.
`$uri` 만 기록하거나 쿼리를 뺀 형태로 기록하세요.

TLS 는 프록시 앞에서 끝냅니다. 사내 표준 리버스 프록시(nginx, Caddy, ALB)
면 됩니다.

```nginx
# Caddy 예
llack.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

## 첨부 파일

`UPLOAD_DIR` 이 첨부 파일이 저장되는 곳입니다. 운영에서는 절대 경로를 주고
**볼륨**으로 받으세요 — 컨테이너를 다시 만들어도 파일이 남아야 합니다.

```yaml
# docker-compose.yml
environment:
  UPLOAD_DIR: /app/var/uploads
volumes:
  - api-var:/app/var
```

systemd 로 돌릴 때는 `UPLOAD_DIR=/var/lib/llack/uploads` 로 두고 그 디렉터리를
백업 대상에 넣으세요.

기본 한도는 20MiB(`MAX_UPLOAD_BYTES`)이고, `image/*` 와 `application/pdf` 만
받습니다.

## 첫 관리자 만들기

1. **앱에서 가입합니다.** 로그인 화면의 "워크스페이스 만들기"를 누르고
   이메일·비밀번호(8자 이상)·이름·팀 이름을 넣습니다. 그 사람이 그 워크스페이스의
   **owner** 가 됩니다. owner 는 곧 admin 권한도 가집니다.
2. **초대 코드를 만듭니다.** 사이드바 위쪽의 워크스페이스 이름 버튼을 눌러
   메뉴를 열고 "팀원 초대"를 고릅니다. 이메일을 넣고 초대를 누르면 코드가
   나옵니다. (owner 와 admin 만 만들 수 있습니다.)
3. **코드를 손으로 전달합니다.** 받은 사람은 로그인 화면의 **초대 코드** 칸에
   그 코드를 넣고 가입(또는 로그인)하면 그 팀에 자동으로 들어갑니다. 공개
   채널에도 자동으로 배치됩니다.
4. 코드는 일주일 뒤 만료되고, 대기 목록에서 회수할 수 있습니다.

## 메일은 없습니다 — 알려두어야 할 사실

이 서버에는 **메일을 보내지 않습니다.** SMTP 설정도, 비밀번호 재설정 메일도,
초대 메일도 없습니다. 초대 코드는 **사람이 직접 전달하는 것**입니다 —
대화창에 붙여 넣거나, 메신저로 보내거나, 만나서 말로 합니다.

비밀번호를 잊어버리면 관리자가 새 초대 코드로 다시 초대해야 합니다(계정
자체의 비밀번호 재설정 경로는 없습니다).

## 알아두어야 할 한계

- **실시간은 프로세스 안**입니다. API 워커를 둘 이상, 인스턴스를 둘 이상
  띄우면 서로의 이벤트가 전달되지 않습니다. 인스턴스당 프로세스 하나.
- **SQLite 는 단일 인스턴스 전용**입니다. 파일에 쓰기 때문에 프로세스가 둘이면 위험합니다.
- **검색은 `LIKE` 스캔**입니다. Postgres 에서도 전문검색은 없습니다.
- **자동 업데이트가 없습니다.** 데스크톱 앱은 새 설치본으로 교체합니다
  ([WINDOWS.md](WINDOWS.md)).
- **백업은 직접 해야 합니다.** 자동으로 해 주는 장치가 없습니다.

## 확인

배포 후 이것만 지나가면 정상입니다.

```bash
curl -s https://llack.example.com/health          # {"status":"ok"}
```

1. 데스크톱 앱으로 로그인한다.
2. 채널 하나에 메시지를 보낸다.
3. 다른 기기(또는 두 번째 창)에서 1초 안에 뜬다.
4. 파일 하나를 올린다 — 이미지가 보인다.
5. 사이드바에서 다른 사람에게 직접 메시지를 보낸다 — presence 가 바뀐다.
