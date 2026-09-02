"""브라우저 UI 종단 스모크 — 실제 백엔드에 대해 헤드리스 Chromium 으로.

백엔드 pytest 가 API 를, 이 스크립트가 "화면에 실제로 보이는가"를 검증합니다.
현재 검사: 이미지 첨부 인라인 미리보기 + 라이트박스, ⌘K 파일 검색,
컴포저 공유 서식, 메시지 공유 버튼.

요구사항 (make smoke-ui 가 아니라 손으로 띄우는 경우):
  - 실행 중인 백엔드:  make dev            (기본 http://127.0.0.1:8000)
  - 실행 중인 웹 모드:  make ui             (기본 http://127.0.0.1:1420)
  - playwright + chromium:  pip install playwright && playwright install chromium

주소가 다르면 LLACK_SMOKE_API / LLACK_SMOKE_UI 로 지정합니다.
시드 데이터(make seed)의 alice 계정과 #개발 채널을 사용합니다.
"""

import asyncio
import base64
import hashlib
import os
import sys
import time

import httpx
from playwright.async_api import async_playwright

API = os.environ.get("LLACK_SMOKE_API", "http://127.0.0.1:8000") + "/api/v1"
UI = os.environ.get("LLACK_SMOKE_UI", "http://127.0.0.1:1420")
EMAIL = "alice@example.com"
PASSWORD = "llack-dev-password"

# 1x1 빨간 픽셀 PNG.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=="
)

checks: list[str] = []


def ok(name: str) -> None:
    checks.append(name)
    print(f"  ✓ {name}")


async def seed_attachment() -> str:
    """PNG 를 올려 #개발 채널에 첨부 메시지로 게시하고 파일명을 돌려줍니다."""
    async with httpx.AsyncClient(base_url=API, timeout=30) as c:
        login = (await c.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})).json()
        c.headers["authorization"] = f"Bearer {login['tokens']['access_token']}"

        workspaces = (await c.get("/workspaces")).json()
        ws = workspaces[0]["id"]
        channels = (await c.get(f"/workspaces/{ws}/channels")).json()
        dev = next(ch for ch in channels if ch.get("name") == "개발")

        name = "스모크-빨간점.png"
        ticket = (
            await c.post(
                f"/workspaces/{ws}/files",
                json={
                    "filename": name,
                    "mime_type": "image/png",
                    "size_bytes": len(PNG),
                    "checksum_sha256": hashlib.sha256(PNG).hexdigest(),
                },
            )
        ).json()
        path = ticket["upload_url"].removeprefix("/api/v1")
        uploaded = await c.put(path, content=PNG, headers={"content-type": "image/png"})
        assert uploaded.status_code == 200, uploaded.text
        file_id = uploaded.json()["id"]

        posted = await c.post(
            f"/channels/{dev['id']}/messages",
            json={"body": "스모크: 이미지 첨부", "file_ids": [file_id]},
        )
        assert posted.status_code in (200, 201), posted.text
        ok("api: 파일 업로드 + 첨부 메시지 게시")
        return name


async def main() -> None:
    filename = await seed_attachment()

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        # 첫 방문은 vite 가 의존성을 그 자리에서 변환하므로 넉넉하게.
        page.set_default_timeout(30000)

        await page.goto(UI)
        await page.fill('input[type="email"]', EMAIL)
        await page.fill('input[type="password"]', PASSWORD)
        await page.click('button[type="submit"]')
        await page.wait_for_selector(".sidebar", state="visible")
        ok("ui: 로그인")

        # ── 이미지 첨부는 이미지로 보인다 ────────────────────────────────
        await page.click('button:has-text("개발")')
        preview = page.locator(".attachment-preview img").last
        await preview.wait_for(state="visible")
        ok("ui: 이미지 첨부 인라인 미리보기가 보임")

        chip = page.locator(f'.attachment:has-text("{filename}")').last
        assert await chip.is_visible(), "칩이 미리보기와 함께 남아 있어야 합니다"
        ok("ui: 다운로드 칩이 미리보기 아래에 그대로 남음")

        await preview.click()
        await page.wait_for_selector(".lightbox img", state="visible")
        ok("ui: 라이트박스가 열림")
        await page.keyboard.press("Escape")
        await page.wait_for_selector(".lightbox", state="detached")
        ok("ui: Esc 로 라이트박스가 닫힘")

        # ── ⌘K 가 파일을 찾는다 ──────────────────────────────────────────
        await page.keyboard.press("Control+k")
        palette_input = page.locator(".palette input")
        if not await palette_input.is_visible():
            await page.keyboard.press("Meta+k")
        await palette_input.wait_for(state="visible")
        await palette_input.fill("스모크-빨간점")
        entry = page.locator(".palette-results button", has_text=filename).first
        await entry.wait_for(state="visible")
        kind = await entry.locator(".palette-kind").inner_text()
        assert kind == "파일", f"kind 라벨이 '파일'이어야 합니다: {kind}"
        ok("ui: ⌘K 가 파일을 '파일' 항목으로 찾음")
        await page.keyboard.press("Escape")

        # ── 컴포저와 메시지의 공유 동선 ──────────────────────────────────
        await page.wait_for_selector('button[aria-label="공유 서식"]')
        await page.click('button[aria-label="공유 서식"]')
        await page.wait_for_selector('.composer-templates >> text=일정 공유')
        ok("ui: 컴포저 공유 서식 메뉴")
        await page.keyboard.press("Escape")

        # The last message is always in view; the first can sit under the
        # sticky channel header, which intercepts the pointer.
        await page.locator("article").last.hover(position={"x": 200, "y": 10})
        share_buttons = page.locator('button[aria-label="다른 대화로 공유"]')
        assert await share_buttons.count() > 0
        ok("ui: 메시지 공유 버튼 존재")

        # ── 채널 설정: 구성원이 보이고, 주제가 저장된다 ──────────────────
        await page.click('button[aria-label="채널 설정"]')
        await page.wait_for_selector(".channel-settings", state="visible")
        await page.wait_for_selector(".member-list li:not(.modal-empty)")
        members = await page.locator(".member-list li").count()
        assert members > 0, "구성원 목록이 비어 있으면 안 됩니다"
        ok(f"ui: 채널 설정 모달 — 구성원 {members}명 로드")

        topic_input = page.locator('.channel-settings label:has-text("주제") input')
        # Unique per run: a repeated stamp would leave the form pristine and
        # the save button honestly disabled.
        stamp = f"스모크가 다녀간 주제 {int(time.time())}"
        await topic_input.fill(stamp)
        await page.click('.channel-settings button:has-text("저장")')
        await page.wait_for_selector(f'.channel-topic:has-text("{stamp}")')
        ok("ui: 주제 수정이 저장되고 머리글에 반영됨")
        await page.keyboard.press("Escape")
        await page.wait_for_selector(".channel-settings", state="detached")

        # ── 웹 앱: URL 하나가 도크 타일이 되고 메인 패널을 채운다 ────────
        await page.click('button[aria-label="앱 추가"]')
        await page.wait_for_selector(".linkapp-form", state="visible")
        # 임베드를 확실히 허용하는 페이지: 백엔드 자신의 API 문서.
        docs_url = API.removesuffix("/api/v1") + "/docs"
        await page.fill('input[aria-label="웹 앱 주소"]', docs_url)
        await page.fill('input[aria-label="웹 앱 이름"]', "스모크 도구")
        await page.click('.linkapp-form button:has-text("추가")')
        tile = page.locator('.dock-app:has-text("스모크 도구")').first
        await tile.wait_for(state="visible")
        ok("ui: URL 추가 → 도크 타일 생성")

        await tile.click()
        await page.wait_for_selector(".webapp-view", state="visible")
        frame_src = await page.locator(".webapp-frame").get_attribute("src")
        assert frame_src and frame_src.startswith(docs_url), frame_src
        ok("ui: 링크 앱이 메인 패널 iframe 으로 열림")

        await page.click('.webapp-header button[aria-label="닫기"]')
        await page.wait_for_selector(".webapp-view", state="detached")
        assert await page.locator(".channel-header").is_visible()
        ok("ui: 닫으면 전사록으로 복귀")

        # ── 환경설정: 기능 안내가 있다 ───────────────────────────────────
        await page.click('button[aria-label="환경설정"]')
        await page.wait_for_selector('.settings:has-text("기능 안내")')
        guide_rows = await page.locator(".settings-guide dt").count()
        assert guide_rows >= 8, f"기능 안내가 빈약합니다: {guide_rows}행"
        ok(f"ui: 환경설정 기능 안내 {guide_rows}행")
        await page.keyboard.press("Escape")

        await browser.close()

    print(f"\n{len(checks)}개 검사 통과")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:  # noqa: BLE001
        print(f"\n실패: {e}", file=sys.stderr)
        sys.exit(1)
