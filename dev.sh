#!/usr/bin/env bash
#
# Llack 개발 환경 원샷 실행 스크립트.
#
#   ./dev.sh            백엔드 준비 → 데스크톱 앱(cargo tauri dev) 실행
#   ./dev.sh web        브라우저용 vite 만 실행 (127.0.0.1:1420)
#   ./dev.sh mobile     Flutter 모바일 앱 실행 (mobile/)
#
# 하는 일:
#   1. 도구 확인 (uv / node / cargo)
#   2. 백엔드 가상환경 + 의존성 설치 (최초 1회)
#   3. 시드 (DB 없을 때만)
#   4. 백엔드 기동 (이미 떠 있으면 그대로 재사용)
#   5. 데스크톱 앱 실행 — 창이 닫히면 이 스크립트도 종료
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
DESKTOP="$ROOT/desktop"
API="http://127.0.0.1:8000"
MODE="${1:-app}"

say() { printf '\033[36m[dev]\033[0m %s\n' "$*"; }
die() { printf '\033[31m[dev] %s\033[0m\n' "$*" >&2; exit 1; }

need() { command -v "$1" >/dev/null 2>&1 || die "$1 이(가) 없습니다 — $2"; }

# ── 1. 도구 확인 ──────────────────────────────────────────────────────
need uv  "brew install uv"
need node "nodejs.org 에서 Node 20+ 설치"
need npm "npm 포함된 Node 설치"

# ── 2. 백엔드 준비 ────────────────────────────────────────────────────
if [ ! -x "$BACKEND/.venv/bin/python" ]; then
  say "백엔드 가상환경 생성 (최초 1회)"
  (cd "$BACKEND" && uv venv --python 3.12)
fi

if ! (cd "$BACKEND" && uv pip install --python .venv/bin/python -e ".[dev]" --quiet); then
  die "백엔드 의존성 설치 실패"
fi

if [ ! -f "$BACKEND/llack.db" ]; then
  say "데모 데이터 시드 (최초 1회)"
  (cd "$BACKEND" && .venv/bin/python scripts/seed.py)
fi

# ── 3. 백엔드 기동 ────────────────────────────────────────────────────
BACKEND_PID=""
cleanup() {
  if [ -n "$BACKEND_PID" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    say "백엔드 종료 (pid $BACKEND_PID)"
    kill "$BACKEND_PID" 2>/dev/null || true
    wait "$BACKEND_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

if curl -fsS "$API/api/v1/health" >/dev/null 2>&1; then
  say "백엔드가 이미 떠 있습니다 ($API) — 그대로 사용합니다"
else
  say "백엔드 시작 ($API)"
  (cd "$BACKEND" && exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000) &
  BACKEND_PID=$!
  for _ in $(seq 1 40); do
    if curl -fsS "$API/api/v1/health" >/dev/null 2>&1; then break; fi
    sleep 0.25
  done
  curl -fsS "$API/api/v1/health" >/dev/null 2>&1 || die "백엔드가 뜨지 않았습니다 (backend/ 에서 직접 확인)"
fi

# ── 4. 프런트엔드 의존성 ──────────────────────────────────────────────
if [ ! -d "$DESKTOP/node_modules" ]; then
  say "프런트엔드 의존성 설치 (최초 1회)"
  (cd "$DESKTOP" && npm install)
fi

# ── 5. 앱 실행 ────────────────────────────────────────────────────────
if [ "$MODE" = "mobile" ]; then
  say "Flutter 모바일 앱 실행 (mobile/)"
  cd "$ROOT/mobile"
  need flutter "flutter.dev 에서 Flutter SDK 설치"
  exec flutter run
fi

if [ "$MODE" = "web" ]; then
  say "vite 실행 → http://127.0.0.1:1420"
  (cd "$DESKTOP" && npm run dev)
  exit 0
fi

cd "$DESKTOP"
if command -v cargo-tauri >/dev/null 2>&1; then
  say "cargo tauri dev 실행 (창이 뜹니다)"
  cargo tauri dev
else
  say "cargo-tauri CLI 가 없어 npm 으로 실행합니다"
  npm run app:dev
fi
