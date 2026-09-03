"""완성도 배치 회귀 스모크 — smoke_team.py 의 자매편.

5인 팀 시뮬레이션이 "이번엔 못 고쳤다"고 남긴 것들을 지킵니다: 파일 모아보기
(필터·검색·공유 위치로 점프), 라이트박스 이전/다음·원본 크기, 활동(스레드·멘션),
이모지 피커와 :단축코드:, 프로필 사진 업로드(비인증 <img> 경로 포함), 워크스페이스
구성원 역할 변경, 로그인 기기 목록, 링크 앱 프로브(임베드 거부 → 새 탭 타일)·
이름 변경·실시간 반영, 업로드 진행률.

요구사항은 smoke_ui.py 와 동일: 실행 중인 백엔드(make dev)와 웹 모드(make ui),
LLACK_SMOKE_API / LLACK_SMOKE_UI 로 주소 지정, make seed 데이터. PIL 필요.
"""

import asyncio
import hashlib
import io
import os
import time

import httpx
from PIL import Image
from playwright.async_api import async_playwright

API = os.environ.get("LLACK_SMOKE_API", "http://127.0.0.1:8000") + "/api/v1"
UI = os.environ.get("LLACK_SMOKE_UI", "http://127.0.0.1:1420")
PW = "llack-dev-password"
results = []


def ok(name):
    results.append(name)
    print(f"  ✓ {name}")


def png_bytes(color, size=(320, 200)):
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


async def api_login(client, email):
    r = await client.post(f"{API}/auth/login", json={"email": email, "password": PW})
    r.raise_for_status()
    data = r.json()
    return {"Authorization": f"Bearer {data['tokens']['access_token']}"}, data["user"]


async def upload(client, headers, ws, name, data, mime="image/png"):
    ticket = (
        await client.post(
            f"{API}/workspaces/{ws}/files",
            headers=headers,
            json={
                "filename": name,
                "mime_type": mime,
                "size_bytes": len(data),
                "checksum_sha256": hashlib.sha256(data).hexdigest(),
            },
        )
    ).json()
    put = await client.put(
        f"{API}{ticket['upload_url'].removeprefix('/api/v1')}",
        headers={**headers, "Content-Type": mime},
        content=data,
    )
    assert put.status_code == 200, put.text
    return ticket["file_id"]


async def login_ui(page, email):
    await page.goto(UI)
    await page.wait_for_selector('input[type="email"]', state="visible")
    await page.fill('input[type="email"]', email)
    await page.fill('input[type="password"]', PW)
    await page.click('button[type="submit"]')
    await page.wait_for_selector(".sidebar", state="visible")


def sidebar_item(page, label):
    return page.locator(f'.sidebar .sidebar-item:has(.sidebar-label:text-is("{label}"))')


async def main():
    stamp = int(time.time())
    async with httpx.AsyncClient(timeout=30) as client, async_playwright() as p:
        alice_h, alice = await api_login(client, "alice@example.com")
        carol_h, carol = await api_login(client, "carol@example.com")
        dave_h, dave = await api_login(client, "dave@example.com")
        workspaces = (await client.get(f"{API}/workspaces", headers=alice_h)).json()
        WS = next(w for w in workspaces if w["slug"] == "acme")["id"]
        channels = (await client.get(f"{API}/workspaces/{WS}/channels", headers=alice_h)).json()
        random_ch = next(c for c in channels if c.get("name") == "random")

        # 준비: 시안 2장 + CSV 한 개를 #random 에 한 메시지로
        f1 = await upload(client, alice_h, WS, f"시안-A-{stamp}.png", png_bytes((165, 0, 52)))
        f2 = await upload(client, alice_h, WS, f"시안-B-{stamp}.png", png_bytes((40, 90, 200)))
        f3 = await upload(client, alice_h, WS, f"지표-{stamp}.csv", b"a,b\n1,2\n", "text/csv")
        posted = (
            await client.post(
                f"{API}/channels/{random_ch['id']}/messages",
                headers=alice_h,
                json={"body": f"시안 2장과 지표 {stamp}", "file_ids": [f1, f2, f3]},
            )
        ).json()
        assert posted["id"]

        browser = await p.chromium.launch()
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()
        page.set_default_timeout(30000)
        await login_ui(page, "alice@example.com")

        # ── 1. 파일 모아보기 ──────────────────────────────────────────────
        await sidebar_item(page, "파일").click()
        await page.wait_for_selector(".file-browser")
        row = page.locator(f'.file-row:has-text("지표-{stamp}.csv")')
        await row.wait_for(state="visible")
        assert "random 에서 공유됨" in await row.locator(".file-where").inner_text()
        ok("파일: 사이드바 '파일' → 목록에 새 파일 + 공유된 채널 표시")
        await page.locator('.file-filters button:text-is("이미지")').click()
        await page.locator(f'.file-row:has-text("지표-{stamp}.csv")').wait_for(state="detached")
        await page.wait_for_selector(f'.file-row:has-text("시안-A-{stamp}.png")')
        ok("파일: '이미지' 필터가 CSV 를 걸러냄")
        await page.locator('.file-filters button:text-is("전체")').click()
        await page.fill(".file-search input", f"지표-{stamp}")
        await page.locator(f'.file-row:has-text("시안-A-{stamp}.png")').wait_for(state="detached")
        await page.wait_for_selector(f'.file-row:has-text("지표-{stamp}.csv")')
        assert await page.locator(".file-row").count() == 1
        ok("파일: 이름 검색이 한 건으로 좁힘")
        await page.locator(f'.file-row:has-text("지표-{stamp}.csv") .file-where').click()
        await page.wait_for_selector(".message.is-spotlit", timeout=20000)
        assert f"시안 2장과 지표 {stamp}" in await page.locator(".message.is-spotlit").inner_text()
        ok("파일: '…에서 공유됨' → 원문 메시지로 점프·스포트라이트")

        # ── 2. 라이트박스: 갤러리 이전/다음·원본 크기 ───────────────────
        await asyncio.sleep(2.6)
        art = page.locator(".message.is-spotlit, article:has-text('시안 2장과 지표')").last
        thumbs = page.locator(f'article:has-text("시안 2장과 지표 {stamp}") .attachment-preview')
        await thumbs.first.wait_for(state="visible", timeout=20000)
        assert await thumbs.count() == 2
        await thumbs.first.click()
        await page.wait_for_selector(".lightbox")
        caption = await page.locator(".lightbox-name").inner_text()
        assert f"시안-A-{stamp}.png" in caption and "1 / 2" in caption, caption
        await page.keyboard.press("ArrowRight")
        await page.wait_for_selector(f'.lightbox-name:has-text("시안-B-{stamp}.png")')
        assert "2 / 2" in await page.locator(".lightbox-name").inner_text()
        ok("라이트박스: 메시지의 이미지 2장을 → 로 넘김 (1/2 → 2/2)")
        await page.locator(".lightbox-stage img").click()
        await page.wait_for_selector(".lightbox figure.is-actual")
        ok("라이트박스: 클릭으로 원본 크기 ↔ 화면 맞춤 전환")
        await page.keyboard.press("Escape")
        await page.wait_for_selector(".lightbox", state="detached")
        _ = art

        # ── 3. 이모지: 반응 피커 + 컴포저 단축코드 ──────────────────────
        target = page.locator(f'article:has-text("시안 2장과 지표 {stamp}")').last
        await target.hover(position={"x": 200, "y": 10})
        await target.locator('button[aria-label="다른 이모지로 반응"]').click()
        await page.wait_for_selector(".emoji-picker")
        await page.fill(".emoji-picker input", "로켓")
        await page.locator(".emoji-grid button").first.click()
        await target.locator('.reaction:has-text("🚀")').wait_for(state="visible")
        ok("이모지: 반응 피커에서 '로켓' 검색 → 🚀 반응")
        box = page.locator(".composer textarea")
        await box.click()
        await box.type(f"릴리스 완료 :tad")
        await page.wait_for_selector(".emoji-suggest")
        await page.keyboard.press("Enter")
        assert "🎉" in await box.input_value()
        await box.type(f":+1: {stamp}")
        await page.keyboard.press("Enter")
        sent = page.locator(f'article:has-text("{stamp}"):has-text("🎉")').last
        await sent.wait_for(state="visible")
        assert "👍" in await sent.inner_text()
        ok("이모지: ':tad' 제안 → 🎉, ':+1:' 은 전송 시 👍 로 변환")

        # ── 4. 활동: 스레드 · 멘션 ───────────────────────────────────────
        await client.post(f"{API}/channels/{random_ch['id']}/join", headers=dave_h)
        reply = await client.post(
            f"{API}/channels/{random_ch['id']}/messages",
            headers=dave_h,
            json={"body": f"@김앨리스 시안 B 가 좋아요 {stamp}", "parent_id": posted["id"]},
        )
        assert reply.status_code == 201, reply.text
        await sidebar_item(page, "활동").click()
        await page.wait_for_selector(".activity-view")
        thread_row = page.locator(f'.activity-row:has-text("시안 2장과 지표 {stamp}")').first
        await thread_row.wait_for(state="visible")
        assert "새 답글 1" in await thread_row.inner_text()
        ok("활동: 내 메시지에 달린 답글이 스레드 탭에 '새 답글 1' 로 표시")
        await thread_row.click()
        await page.wait_for_selector(f'.thread-pane:has-text("시안 B 가 좋아요 {stamp}")')
        ok("활동: 스레드 항목 클릭 → 채널 이동 + 스레드 열림")
        await sidebar_item(page, "활동").click()
        await page.locator('.file-filters button:has-text("멘션")').click()
        mention_row = page.locator(f'.activity-row:has-text("시안 B 가 좋아요 {stamp}")').first
        await mention_row.wait_for(state="visible")
        assert "스레드" in await mention_row.inner_text()
        ok("활동: 한글 이름 멘션이 멘션 탭에 (스레드 표시와 함께) 나옴")

        # ── 5. 프로필 사진 ───────────────────────────────────────────────
        await page.click('button[aria-label="환경설정"]')
        await page.set_input_files('input[aria-label="프로필 사진 파일"]', {
            "name": "me.png", "mimeType": "image/png", "buffer": png_bytes((20, 120, 80), (400, 300)),
        })
        await page.wait_for_selector('.banner:has-text("프로필 사진을 바꿨습니다")')
        me = (await client.get(f"{API}/me", headers=alice_h)).json()
        assert me["avatar_url"] and me["avatar_url"].startswith("/api/v1/users/"), me["avatar_url"]
        public = await client.get(API.removesuffix("/api/v1") + me["avatar_url"])
        assert public.status_code == 200 and public.headers["content-type"].startswith("image/")
        assert "immutable" in public.headers.get("cache-control", "")
        src = await page.locator(".settings-avatar-row .avatar img").get_attribute("src")
        assert src and me["avatar_url"] in src
        ok("아바타: 업로드 → 서버 상대 경로 → 비인증 <img> 로 불러옴 (immutable 캐시)")
        await page.locator('.settings-avatar-actions button:text-is("제거")').click()
        await page.wait_for_selector('.banner:has-text("프로필 사진을 지웠습니다")')
        assert (await client.get(f"{API}/me", headers=alice_h)).json()["avatar_url"] is None
        ok("아바타: 제거 → 이니셜로 복귀")

        # ── 6. 구성원 역할 · 로그인 기기 ─────────────────────────────────
        members_ul = page.locator(".workspace-members")
        dave_row = members_ul.locator(f'li:has-text("{dave["display_name"]}")')
        await dave_row.wait_for(state="visible")
        await dave_row.locator("select").select_option("admin")
        await page.wait_for_selector('.banner:has-text("관리자로 바꿨습니다")')
        members = (await client.get(f"{API}/workspaces/{WS}/members", headers=alice_h)).json()
        assert next(m for m in members if m["user"]["id"] == dave["id"])["role"] == "admin"
        await dave_row.locator("select").select_option("member")
        await page.wait_for_selector('.banner:has-text("구성원으로 바꿨습니다")')
        ok("구성원: 소유자가 역할을 관리자↔구성원으로 바꿈 (API 일치)")
        await page.locator('.settings-sessions button:has-text("보기")').click()
        await page.wait_for_selector('.session-list li.is-current:has-text("이 기기")')
        ok("로그인 기기: 목록에 '이 기기' 가 표시됨")
        await page.keyboard.press("Escape")

        # ── 7. 링크 앱: 구성원이 프로브 → 새 탭 타일 → 이름 변경 → 실시간 ─
        ctx2 = await browser.new_context(viewport={"width": 1440, "height": 900})
        cpage = await ctx2.new_page()
        cpage.set_default_timeout(30000)
        await login_ui(cpage, "carol@example.com")
        dock_before = await page.locator(".dock-tile, .dock button").count()
        await cpage.click('button[aria-label="앱 추가"], button[title="앱 추가"]')
        await cpage.wait_for_selector(".app-directory")
        await cpage.fill('input[aria-label="웹 앱 주소"]', "https://github.com")
        await cpage.fill('input[aria-label="웹 앱 이름"]', f"깃허브 {stamp}")
        await cpage.locator('.linkapp-row button:has-text("추가")').click()
        await cpage.wait_for_selector(".linkapp-blocked", timeout=25000)
        ok("링크 앱: 구성원이 github.com 추가 → 프로브가 임베드 거부를 미리 알림")
        await cpage.locator('button:has-text("새 탭으로 여는 앱으로 추가")').click()
        await cpage.wait_for_selector(".app-directory", state="detached")
        installations = (await client.get(f"{API}/workspaces/{WS}/apps", headers=carol_h)).json()
        mine = next(i for i in installations if i["app"]["name"] == f"깃허브 {stamp}")
        assert mine["config"].get("open_mode") == "external" and mine["installed_by"] == carol["id"]
        ok("링크 앱: open_mode=external 로 저장, installed_by 기록")
        await asyncio.sleep(1.5)
        assert await page.locator(f'[title*="깃허브 {stamp}"], [aria-label*="깃허브 {stamp}"]').count() >= 1
        ok("링크 앱: 다른 사람(alice) 도크에 새로고침 없이 타일이 나타남")
        await cpage.locator(f'[title*="깃허브 {stamp}"], [aria-label*="깃허브 {stamp}"]').first.click()
        await cpage.wait_for_selector(".webapp-external")
        assert await cpage.locator(".webapp-frame").count() == 0
        ok("링크 앱: 새 탭 타일은 빈 iframe 대신 '새 탭에서 열기' 카드")
        await cpage.click('button[aria-label="이름 바꾸기"]')
        await cpage.fill(".webapp-rename input", f"GitHub {stamp}")
        await cpage.keyboard.press("Enter")
        await cpage.wait_for_selector('.banner:has-text("이름을")')
        await asyncio.sleep(1.5)
        assert await page.locator(f'[title*="GitHub {stamp}"], [aria-label*="GitHub {stamp}"]').count() >= 1
        ok("링크 앱: 추가한 사람이 이름 변경 → 상대 도크에도 실시간 반영")
        await cpage.click('button[aria-label="도크에서 빼기"]')
        await cpage.locator('button:has-text("도크에서 빼기")').last.click()
        await cpage.wait_for_selector('.banner:has-text("도크에서 뺐습니다")')
        _ = dock_before
        ok("링크 앱: 추가한 사람이 스스로 제거")
        await ctx2.close()

        # ── 8. 업로드 진행률 ─────────────────────────────────────────────
        await sidebar_item(page, "random").click()
        await page.wait_for_selector(".composer textarea")

        async def slow(route):
            await asyncio.sleep(1.2)
            await route.continue_()

        await page.route("**/files/*/content", slow)
        await page.set_input_files(
            'input[type="file"]',
            {"name": f"big-{stamp}.png", "mimeType": "image/png", "buffer": png_bytes((0, 0, 0), (1600, 1200))},
        ) if await page.locator('input[type="file"]').count() > 0 else None
        # 파일 선택기가 숨겨진 input 이 아닐 수 있으니 붙여넣기 경로로도 시도
        await page.locator(".composer textarea").focus()
        await page.evaluate(
            """async () => {
              const res = await fetch('data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==');
              const blob = await res.blob();
              const file = new File([blob], 'paste.png', { type: 'image/png' });
              const dt = new DataTransfer(); dt.items.add(file);
              const ev = new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true });
              document.querySelector('.composer textarea').dispatchEvent(ev);
            }"""
        )
        await page.wait_for_selector(".composer-uploads progress", timeout=5000)
        ok("업로드 진행률: 전송 중 진행 막대가 보임")
        await page.wait_for_selector('.composer-attachments li:has-text("paste.png"), .composer-attachments li:has-text("스크린샷")', timeout=15000)
        await page.unroute("**/files/*/content")
        ok("업로드 진행률: 완료 후 첨부 칩으로 전환")

        await ctx.close()
        await browser.close()

    print(f"\n{len(results)}개 검증 통과")


asyncio.run(main())
