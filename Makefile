# Llack — 개발 명령 모음
#
# 기본 개발 스택은 의존성이 없습니다: SQLite + 프로세스 내 pub/sub + 로컬 파일.
# `make compose-up` 은 Postgres/Redis/MinIO 로 프로덕션과 같은 경로를 실행합니다.

SHELL := /bin/bash
.DEFAULT_GOAL := help

BACKEND := backend
DESKTOP := desktop
SDK     := packages/llack-app-sdk
PIP     := $(BACKEND)/.venv/bin/pip
CARGO   := $(HOME)/.cargo/bin/cargo

# 개발용 기본값. 실제 배포에서는 반드시 덮어쓰세요.
export LLACK_DATABASE_URL ?= sqlite+aiosqlite:///./var/llack-dev.db
export LLACK_SECRET_KEY   ?= dev-secret-not-for-production-0123456789
export LLACK_ENV          ?= development

## ── 도움말 ────────────────────────────────────────────────────────────

.PHONY: help
help: ## 사용 가능한 명령 보기
	@grep -hE '^[a-zA-Z0-9_.-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

## ── 설치 ──────────────────────────────────────────────────────────────

.PHONY: setup
setup: setup-backend setup-desktop setup-sdk ## 전체 의존성 설치

.PHONY: setup-backend
setup-backend: ## 백엔드 가상환경 생성 및 의존성 설치
	cd $(BACKEND) && (python3.11 -m venv .venv || python3 -m venv .venv)
	cd $(BACKEND) && .venv/bin/pip install -q --upgrade pip setuptools wheel
	cd $(BACKEND) && .venv/bin/pip install -q -e ".[dev]"
	cd $(BACKEND) && .venv/bin/pip install -q asgi-lifespan anyio

.PHONY: setup-desktop
setup-desktop: ## 데스크톱 프론트엔드 의존성 설치
	cd $(DESKTOP) && npm install --no-audit --no-fund

.PHONY: setup-sdk
setup-sdk: ## 미니앱 SDK 설치 및 빌드
	cd $(SDK) && npm install --no-audit --no-fund && npm run build

## ── 실행 ──────────────────────────────────────────────────────────────

.PHONY: dev
dev: migrate ## 백엔드 개발 서버 실행 (외부 의존성 없음)
	cd $(BACKEND) && .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

.PHONY: desktop
desktop: ## 데스크톱 앱 실행 (webkit2gtk 등 시스템 의존성 필요)
	cd $(DESKTOP) && npm run app:dev

.PHONY: ui
ui: ## 프론트엔드만 브라우저에서 실행 (Tauri 없이 UI 확인)
	cd $(DESKTOP) && npm run dev

.PHONY: example-app
example-app: ## 예제 미니앱을 5180 포트로 서빙
	cd examples/apps/standup && python3 -m http.server 5180

## ── 데이터베이스 ──────────────────────────────────────────────────────

.PHONY: migrate
migrate: ## 마이그레이션 적용
	cd $(BACKEND) && mkdir -p var && .venv/bin/alembic upgrade head

.PHONY: migration
migration: ## 새 마이그레이션 생성 (m="설명")
	@test -n "$(m)" || { echo 'm="설명" 을 지정해주세요'; exit 1; }
	cd $(BACKEND) && .venv/bin/alembic revision --autogenerate -m "$(m)"

.PHONY: seed
seed: migrate ## 개발용 시드 데이터 생성 (반복 실행 안전)
	cd $(BACKEND) && .venv/bin/python -m scripts.seed

.PHONY: reset-db
reset-db: ## 개발 DB 삭제 후 재생성 + 시드
	rm -f $(BACKEND)/var/llack-dev.db*
	$(MAKE) seed

## ── 검증 ──────────────────────────────────────────────────────────────

.PHONY: test
test: test-backend test-core ## 전체 테스트

.PHONY: test-backend
test-backend: ## 백엔드 테스트 (77개)
	cd $(BACKEND) && .venv/bin/python -m pytest -q

.PHONY: test-core
test-core: ## Rust 코어 테스트 (50개)
	cd $(DESKTOP) && $(CARGO) test -p llack-core

.PHONY: smoke
smoke: ## 실행 중인 서버에 대해 실시간/미니앱 종단 검증
	cd $(BACKEND) && .venv/bin/python scripts/smoke_realtime.py
	cd $(BACKEND) && .venv/bin/python scripts/smoke_apps.py

.PHONY: lint
lint: ## 린트 및 타입 검사
	cd $(BACKEND) && .venv/bin/ruff check app tests scripts
	$(BACKEND)/.venv/bin/ruff check scripts
	cd $(DESKTOP) && npx tsc --noEmit
	cd $(DESKTOP) && $(CARGO) clippy -p llack-core -- -D warnings
	cd $(SDK) && npx tsc -p tsconfig.json --noEmit

.PHONY: fmt
fmt: ## 자동 포매팅
	cd $(BACKEND) && .venv/bin/ruff check app tests scripts --fix
	$(BACKEND)/.venv/bin/ruff check scripts --fix
	cd $(DESKTOP) && $(CARGO) fmt

.PHONY: icons
icons: ## 데스크톱 아이콘 세트 재생성
	python3 scripts/generate_icons.py

.PHONY: build
build: ## 프론트엔드 및 SDK 프로덕션 빌드
	cd $(SDK) && npm run build
	cd $(DESKTOP) && npm run build

.PHONY: check
check: lint test build ## CI 가 실행하는 모든 검사

## ── Docker ────────────────────────────────────────────────────────────

.PHONY: compose-up
compose-up: ## Postgres/Redis/MinIO + API 실행
	docker compose up -d --build
	@echo "API: http://localhost:8000/docs · MinIO: http://localhost:9001"

.PHONY: compose-down
compose-down: ## 컨테이너 중지
	docker compose down

.PHONY: compose-logs
compose-logs: ## API 로그 보기
	docker compose logs -f api

.PHONY: compose-nuke
compose-nuke: ## 컨테이너와 볼륨까지 삭제
	docker compose down -v

## ── 정리 ──────────────────────────────────────────────────────────────

.PHONY: clean
clean: ## 빌드 산출물 삭제
	rm -rf $(DESKTOP)/dist $(SDK)/dist
	rm -rf $(BACKEND)/.pytest_cache $(BACKEND)/.ruff_cache
	find $(BACKEND) -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
