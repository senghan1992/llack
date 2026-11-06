# Llack — 개발 명령 모음
#
# 스택은 셋입니다: FastAPI 백엔드(python/uv), React+Vite 프런트엔드(npm),
# Tauri 2 데스크톱 셸(Rust/cargo). 외부 인프라가 필요 없습니다 — SQLite 한 파일
# 로 개발하고, Postgres 는 운영 배포에서만 씁니다.
#
# `make help` 로 전체 목록을 볼 수 있습니다.

SHELL := /bin/bash
.DEFAULT_GOAL := help

BACKEND  := backend
DESKTOP  := desktop
SHELL_DIR := $(DESKTOP)/src-tauri

## ── 도움말 ────────────────────────────────────────────────────────────

.PHONY: help
help: ## 사용 가능한 명령 보기
	@grep -hE '^[a-zA-Z0-9_.-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

## ── 설치 ──────────────────────────────────────────────────────────────

.PHONY: setup
setup: setup-backend setup-desktop ## 전체 의존성 설치 (백엔드 가상환경 + 프런트엔드)

.PHONY: setup-backend
setup-backend: ## 백엔드 가상환경 생성 및 의존성 설치 (uv)
	cd $(BACKEND) && uv venv --python 3.12
	cd $(BACKEND) && uv pip install --python .venv -e ".[dev]"

.PHONY: setup-desktop
setup-desktop: ## 프런트엔드 의존성 설치 (npm ci)
	cd $(DESKTOP) && npm ci

## ── 실행 ──────────────────────────────────────────────────────────────

.PHONY: dev
dev: ## 백엔드 API 실행 (127.0.0.1:8000, 재시작 옵션 있음)
	cd $(BACKEND) && .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

.PHONY: dev-desktop
dev-desktop: ## Tauri 데스크톱 앱 실행 (창이 뜹니다 — 백엔드가 먼저 떠 있어야 합니다)
	cd $(DESKTOP) && npm run app:dev

.PHONY: dev-web
dev-web: ## 브라우저에서 프런트엔드만 실행 (vite, 127.0.0.1:1420)
	cd $(DESKTOP) && npm run dev

.PHONY: desktop-headless
desktop-headless: ## 실제 데스크톱 앱을 Xvfb 위에서 실행하고 스크린샷 (xvfb·ffmpeg 필요)
	./scripts/desktop-headless.sh --login

.PHONY: seed
seed: ## 데모 워크스페이스 시드 (한빛 — 반복 실행해도 안전합니다)
	cd $(BACKEND) && .venv/bin/python scripts/seed.py

## ── 검증 ──────────────────────────────────────────────────────────────

.PHONY: test
test: ## 백엔드 테스트 (pytest)
	cd $(BACKEND) && .venv/bin/pytest -q

.PHONY: lint
lint: ## 린트 · 포맷 검사 · 타입 검사
	cd $(BACKEND) && .venv/bin/ruff check app tests scripts
	cd $(BACKEND) && .venv/bin/ruff format --check .
	cd $(DESKTOP) && npm run typecheck

.PHONY: format
format: ## 자동 포맷 (ruff fix + ruff format)
	cd $(BACKEND) && .venv/bin/ruff check app tests scripts --fix
	cd $(BACKEND) && .venv/bin/ruff format .

.PHONY: contrast
contrast: ## 글자 대비 점검 (hover · 정적) — 실행 중인 앱과 playwright 필요
	python3 scripts/check-contrast.py

## ── 빌드 ──────────────────────────────────────────────────────────────

.PHONY: build
build: ## 프런트엔드 번들 + 데스크톱 셸 빌드
	cd $(DESKTOP) && npm run build
	cd $(SHELL_DIR) && cargo build --release

.PHONY: clean
clean: ## 빌드 산출물 삭제
	rm -rf $(DESKTOP)/dist $(DESKTOP)/target $(SHELL_DIR)/target
	rm -rf $(BACKEND)/.pytest_cache $(BACKEND)/.ruff_cache
	find $(BACKEND) -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true

## ── 데이터베이스 ──────────────────────────────────────────────────────

.PHONY: db-reset
db-reset: ## 개발용 SQLite DB 삭제 (다음 실행 때 자동으로 다시 만들어집니다)
	rm -f $(BACKEND)/llack.db $(BACKEND)/llack.db-wal $(BACKEND)/llack.db-shm

## ── Docker ────────────────────────────────────────────────────────────

.PHONY: compose-up
compose-up: ## Postgres + API 컨테이너 실행 (docker compose)
	docker compose up -d --build

.PHONY: compose-down
compose-down: ## 컨테이너 중지
	docker compose down

.PHONY: compose-logs
compose-logs: ## API 로그 보기
	docker compose logs -f api
