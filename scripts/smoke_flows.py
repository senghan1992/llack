"""핵심 사용 흐름 종단 스모크 — smoke_ui.py 의 자매편.

smoke_ui.py 가 개별 위젯을 검증한다면, 이 스크립트는 시뮬레이션 QA 가 찾은
결함의 회귀를 지킵니다: 스크롤백(과거 메시지 열람), 검색 결과→메시지 점프,
핀 고정/목록/점프, 프로필 저장, 로그아웃, 초대 링크 E2E(생성→가입→자동 수락),
그리고 레이트 리밋 아웃박스의 무유실 자동 재전송.

요구사항은 smoke_ui.py 와 동일: 실행 중인 백엔드(make dev)와 웹 모드(make ui),
LLACK_SMOKE_API / LLACK_SMOKE_UI 로 주소 지정, make seed 데이터.
"""

import asyncio
import os
import sys
import time

import httpx
from playwright.async_api import async_playwright

API = os.environ.get("LLACK_SMOKE_API", "http://127.0.0.1:8000") + "/api/v1"
UI = os.environ.get("LLACK_SMOKE_UI", "http://127.0.0.1:1420")
PW = "llack-dev-password"

results = []


def ok(name):
    results.append(name)
    print(f"  ✓ {name}")


async def login_ui(page, email):
    await page.goto(UI)
    await page.wait_for_selector('input[type="email"]', state="visible")
    await page.fill('input[type="email"]', email)
    await page.fill('input[type="password"]', PW)
    await page.click('button[type="submit"]')
    await page.wait_for_selector(".sidebar", state="visible")


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()

        # ── 1. 스크롤백: 위로 스크롤하면 이전 페이지가 로드된다 ──────────
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()
        page.set_default_timeout(30000)
        await login_ui(page, "alice@example.com")
        await page.click('.sidebar button:has-text("개발")')
        await page.wait_for_selector("article", state="visible")
        before = await page.locator("article").count()
        metrics = await page.evaluate(
            "() => { const t = document.querySelector('.transcript'); return [t.scrollHeight, t.clientHeight]; }"
        )
        assert metrics[0] > metrics[1], f"transcript 가 스크롤 불가: {metrics}"
        await page.evaluate("document.querySelector('.transcript').scrollTop = 0")
        await asyncio.sleep(2.5)
        after = await page.locator("article").count()
        assert after > before, f"이전 페이지 미로드: {before} -> {after}"
        ok(f"스크롤백: scrollHeight>{metrics[1]}px, 위로 스크롤 시 {before}→{after}개 로드")

        # ── 2. 검색 점프: 결과 클릭 → 해당 메시지 스포트라이트 ───────────
        await page.keyboard.press("Control+k")
        await page.locator(".palette input").fill("옛날기록-001")
        entry = page.locator('.palette-results button:has-text("옛날기록-001")').first
        await entry.wait_for(state="visible")
        await entry.click()
        await page.wait_for_selector(".message.is-spotlit", timeout=25000)
        spotlit = await page.locator(".message.is-spotlit").inner_text()
        assert "옛날기록-001" in spotlit
        ok("검색 점프: 오래된 메시지까지 페이지백 후 스포트라이트")

        # ── 3. 핀: 고정 → 머리글 목록 → 점프 ────────────────────────────
        await asyncio.sleep(2.6)  # 스포트라이트 종료 대기
        await page.evaluate(
            "() => { const t = document.querySelector('.transcript'); t.scrollTop = t.scrollHeight; }"
        )
        pin_tag = f"고정 검증 {int(time.time())}"
        await page.fill(".composer textarea", pin_tag)
        await page.keyboard.press("Enter")
        target = page.locator(f'article:has-text("{pin_tag}")').last
        await target.wait_for(state="visible")
        await target.hover(position={"x": 200, "y": 10})
        await target.locator('button[aria-label="채널에 고정"]').click()
        await page.click('button[aria-label="고정된 메시지"]')
        await page.wait_for_selector(".pinned-rows li", state="visible")
        ok("핀: 메시지 고정 → 머리글의 고정 목록에 표시")
        await page.locator(".pinned-rows li button").first.click()
        await page.wait_for_selector(".message.is-spotlit", timeout=15000)
        ok("핀: 목록에서 클릭 → 메시지로 점프")

        # ── 4. 프로필 저장 + 로그아웃 버튼 ───────────────────────────────
        await asyncio.sleep(2.6)
        await page.click('button[aria-label="환경설정"]')
        status_field = page.locator('.settings label:has-text("상태 문구") input')
        stamp = f"검증 중 {int(time.time())}"
        await status_field.fill(stamp)
        await page.locator('.settings button:has-text("저장")').first.click()
        await page.wait_for_selector('.banner:has-text("프로필을 저장했습니다"), :text("프로필을 저장했습니다")')
        ok("프로필: 상태 문구 저장 배너")
        logout = page.locator('.settings button:has-text("로그아웃")')
        await logout.click()
        await page.wait_for_selector('input[type="email"]', state="visible", timeout=15000)
        ok("로그아웃 버튼: 로그인 화면으로 복귀")
        await ctx.close()

        # ── 5. 초대 E2E: 링크 생성 → 새 사용자가 링크로 가입 → 자동 참여 ─
        ctx_admin = await browser.new_context(viewport={"width": 1440, "height": 900})
        admin = await ctx_admin.new_page()
        admin.set_default_timeout(30000)
        await login_ui(admin, "alice@example.com")
        await admin.click('button[aria-label="환경설정"]')
        await admin.fill('input[aria-label="초대할 이메일"]', f"invitee{int(time.time())}@example.com")
        await admin.click('button:has-text("초대 링크 만들기")')
        await admin.wait_for_selector(".invite-list li", state="visible")
        link = await admin.locator(".invite-info span").first.inner_text()
        assert link.startswith("http"), link
        ok(f"초대: 관리자 UI 에서 웹 링크 생성 ({link[:44]}…)")
        await ctx_admin.close()

        ctx_new = await browser.new_context(viewport={"width": 1440, "height": 900})
        newbie = await ctx_new.new_page()
        newbie.set_default_timeout(30000)
        await newbie.goto(link)
        note = await newbie.locator(".signin-plate").inner_text()
        assert "초대" in note, "초대 안내 문구가 보여야 합니다"
        await newbie.click('button:has-text("계정이 없으신가요?")')
        stamp2 = int(time.time())
        await newbie.fill('input[type="email"]', f"invitee{stamp2}@example.com")
        await newbie.fill('input[type="password"]', "invitee-password-123")
        await newbie.locator('label:has-text("이름") input').first.fill("초대검증")
        await newbie.locator('button[type="submit"]').click()
        await newbie.wait_for_selector('.sidebar:has-text("채널")', timeout=20000)
        body = await newbie.locator(".sidebar").inner_text()
        assert "general" in body or "채널" in body
        ok("초대: 링크로 가입 → 초대 자동 수락 → 워크스페이스 진입")
        await ctx_new.close()

        # ── 6. 429 아웃박스: 40연발이 자동 드레인으로 전량 도착 ──────────
        async with httpx.AsyncClient(base_url=API, timeout=30) as c:
            login = (await c.post("/auth/login", json={"email": "bob@example.com", "password": PW})).json()
            c.headers["authorization"] = f"Bearer {login['tokens']['access_token']}"
            ws = (await c.get("/workspaces")).json()[0]["id"]
            channels = (await c.get(f"/workspaces/{ws}/channels")).json()
            dev = next(ch for ch in channels if ch.get("name") == "개발")

        ctx_bob = await browser.new_context(viewport={"width": 1440, "height": 900})
        bob = await ctx_bob.new_page()
        bob.set_default_timeout(30000)
        await login_ui(bob, "bob@example.com")
        await bob.click('.sidebar button:has-text("개발")')
        await bob.wait_for_selector(".composer textarea")
        run_tag = f"연발{int(time.time())}"
        for i in range(40):
            await bob.fill(".composer textarea", f"{run_tag}-{i:02d}")
            await bob.keyboard.press("Enter")
        # 자동 드레인이 레이트 리밋을 넘길 시간.
        await asyncio.sleep(22)
        async with httpx.AsyncClient(base_url=API, timeout=30) as c:
            login = (await c.post("/auth/login", json={"email": "dave@example.com", "password": PW})).json()
            c.headers["authorization"] = f"Bearer {login['tokens']['access_token']}"
            page1 = (await c.get(f"/channels/{dev['id']}/messages?limit=100")).json()
            bodies = [m["body"] for m in page1["items"]]
        arrived = sum(1 for b in bodies if b.startswith(run_tag))
        assert arrived == 40, f"유실 발생: 40개 중 {arrived}개만 도착"
        ok("429 아웃박스: 40연발 전량 자동 전송 (유실 0)")
        await ctx_bob.close()

        await browser.close()

    print(f"\n{len(results)}개 검증 통과")


try:
    asyncio.run(main())
except Exception as e:  # noqa: BLE001
    print(f"\n실패: {e}", file=sys.stderr)
    sys.exit(1)
