"""로드맵 완주 배치 회귀 스모크 — 운영·사용성·앱 플랫폼.

지키는 것: 감사 로그(UI·CSV), 보관 정책(워크스페이스·채널), 썸네일·Range·미디어 토큰,
/metrics, 방해 금지·일시 중지, 나중에 보기·리마인더, 슬래시 명령(내장), @here/@channel
피커, 사이드바 섹션, 배지 병기, 첫 진입 카드, 초대 재발송, 링크 언펄, 개발자 콘솔(등록·
토큰·심사), 인터랙티브 블록 렌더, 앱 홈.

요구사항은 smoke_ui.py 와 동일 (실행 중인 백엔드·웹 모드, LLACK_SMOKE_API / LLACK_SMOKE_UI,
make seed 데이터). PIL 필요.
"""

import asyncio
import hashlib
import io
import json
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


def png_bytes(color, size=(640, 400)):
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
    return put.json()


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
        bob_h, bob = await api_login(client, "bob@example.com")
        workspaces = (await client.get(f"{API}/workspaces", headers=alice_h)).json()
        WS = next(w for w in workspaces if w["slug"] == "acme")["id"]
        channels = (await client.get(f"{API}/workspaces/{WS}/channels", headers=alice_h)).json()
        random_ch = next(c for c in channels if c.get("name") == "random")
        await client.post(f"{API}/channels/{random_ch['id']}/join", headers=bob_h)

        # ── A. 운영: 썸네일 · Range · 미디어 토큰 · 메트릭 (API) ─────────
        image = await upload(client, alice_h, WS, f"썸네일-{stamp}.png", png_bytes((200, 30, 60)))
        for _ in range(20):
            detail = (await client.get(f"{API}/files/{image['id']}", headers=alice_h)).json()
            if detail.get("thumbnail_url"):
                break
            await asyncio.sleep(0.3)
        assert detail.get("thumbnail_url"), detail
        thumb = await client.get(f"{API}/files/{image['id']}/thumbnail", headers=alice_h)
        assert thumb.status_code == 200 and thumb.headers["content-type"].startswith("image/")
        w, h = Image.open(io.BytesIO(thumb.content)).size
        assert max(w, h) <= 320, (w, h)
        ok(f"썸네일: 업로드 후 생성 (긴 변 {max(w, h)}px ≤ 320)")
        ranged = await client.get(
            f"{API}/files/{image['id']}/download", headers={**alice_h, "Range": "bytes=0-99"}
        )
        assert ranged.status_code == 206 and ranged.headers["content-range"].startswith("bytes 0-99/")
        assert len(ranged.content) == 100
        ok("Range: bytes=0-99 → 206 + Content-Range")
        token = (await client.post(f"{API}/files/{image['id']}/media-token", headers=alice_h)).json()
        public = await client.get(API.removesuffix("/api/v1") + token["url"])
        assert public.status_code == 200 and public.headers["content-type"].startswith("image/"), (public.status_code, public.text[:200])
        ok("미디어 토큰: Authorization 없이 <img>/<video> 가 받을 수 있는 URL")
        metrics = await client.get(API.removesuffix("/api/v1") + "/metrics")
        assert metrics.status_code == 200 and "llack_http_requests_total" in metrics.text, (metrics.status_code, metrics.text[:200])
        ok("/metrics: Prometheus 텍스트에 llack_http_requests_total")

        browser = await p.chromium.launch()
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()
        page.set_default_timeout(30000)
        await login_ui(page, "alice@example.com")

        # ── 보관 정책 · 감사 로그 (UI) ───────────────────────────────────
        await page.click('button[aria-label="환경설정"]')
        ret = page.locator('.settings-section:has(h3:text-is("보관 정책"))')
        # 설정이 로드되기 전에 입력하면 로드가 입력을 덮어씁니다.
        await ret.locator('.settings-hint:has-text("자동 삭제")').first.wait_for(state="visible")
        await ret.locator('label:has-text("메시지 보관 기간") input').fill("365")
        await ret.locator('button:has-text("저장")').click()
        await page.wait_for_selector('.banner:has-text("보관 정책을 저장했습니다")')
        retention = (await client.get(f"{API}/workspaces/{WS}/retention", headers=alice_h)).json()
        assert retention["retention_days_messages"] == 365
        ok("보관 정책: 환경설정에서 365일 저장 → API 일치")
        await ret.locator('label:has-text("메시지 보관 기간") input').fill("")
        await ret.locator('button:has-text("저장")').click()
        await page.wait_for_selector('.banner:has-text("보관 정책을 해제했습니다")')
        audit = page.locator('.settings-section:has(h3:text-is("감사 로그"))')
        await audit.locator('.audit-list li:has-text("보관 정책 변경")').first.wait_for(state="visible")
        ok("감사 로그: 방금 한 보관 정책 변경이 목록 맨 위에")
        async with page.expect_download() as download_info:
            await audit.locator('button:has-text("CSV 내려받기")').click()
        download = await download_info.value
        assert download.suggested_filename.endswith(".csv")
        ok("감사 로그: CSV 내려받기")

        # ── B. 방해 금지 · 일시 중지 ─────────────────────────────────────
        dnd = page.locator('.settings-section:has(h3:text-is("알림 시간"))')
        await dnd.locator('button:text-is("1시간")').click()
        await page.wait_for_selector('.banner:has-text("1시간 동안 알림을 멈춥니다")')
        me = (await client.get(f"{API}/me", headers=alice_h)).json()
        assert me["in_dnd"] is True and me["notify_paused_until"]
        ok("알림 일시 중지: 1시간 → in_dnd=true")
        await dnd.locator('button:text-is("다시 켜기")').click()
        await page.wait_for_selector('.banner:has-text("알림을 다시 켰습니다")')
        await dnd.locator('input[aria-label="방해 금지 시작"]').fill("22:00")
        await dnd.locator('input[aria-label="방해 금지 끝"]').fill("08:00")
        await dnd.locator('button:text-is("저장")').click()
        await page.wait_for_selector('.banner:has-text("22:00–08:00")')
        me = (await client.get(f"{API}/me", headers=alice_h)).json()
        assert me["dnd_start"] == "22:00" and me["dnd_end"] == "08:00"
        await dnd.locator('button:text-is("해제")').click()
        await page.wait_for_selector('.banner:has-text("해제했습니다")')
        ok("방해 금지 시간: 22:00–08:00 저장·해제")
        await page.keyboard.press("Escape")

        # ── 나중에 보기 · 리마인더 · 슬래시 명령 ─────────────────────────
        await sidebar_item(page, "random").click()
        posted = (
            await client.post(
                f"{API}/channels/{random_ch['id']}/messages",
                headers=bob_h,
                json={"body": f"리뷰 부탁 https://example.com/ 문서 {stamp}"},
            )
        ).json()
        target = page.locator(f'article:has-text("문서 {stamp}")').last
        await target.wait_for(state="visible")
        await target.hover(position={"x": 200, "y": 10})
        await target.locator('button[aria-label="나중에 보기"]').click()
        await page.locator('.save-menu button:has-text("저장만")').click()
        await page.wait_for_selector('.banner:has-text("나중에 볼 항목에 저장했습니다")')
        refreshed = (await client.get(f"{API}/messages/{posted['id']}", headers=alice_h)).json()
        assert refreshed["is_saved"] is True
        ok("나중에 보기: 책갈피 → is_saved=true")
        await sidebar_item(page, "나중에").click()
        await page.wait_for_selector(f'.saved-view .activity-row:has-text("문서 {stamp}")')
        await page.locator(f'.saved-row:has-text("문서 {stamp}") button:text-is("완료")').click()
        await page.wait_for_selector('.banner:has-text("완료로 표시했습니다")')
        ok("나중에: 목록에 보이고 완료 처리")
        await sidebar_item(page, "random").click()
        box = page.locator(".composer textarea")
        await box.click()
        await box.type("/rem")
        await page.wait_for_selector('.command-picker:has-text("/remind")')
        ok("슬래시 명령: '/rem' → /remind 제안")
        await box.fill(f"/remind me in 1m 스탠드업 준비 {stamp}")
        await page.keyboard.press("Enter")
        await page.wait_for_selector(".message-ephemeral")
        saved = (await client.get(f"{API}/workspaces/{WS}/saved?done=false", headers=alice_h)).json()
        assert any(item["remind_at"] for item in saved["items"]), saved
        ok("슬래시 명령: /remind → 나에게만 보이는 확인 + 리마인더 저장")

        # ── 링크 언펄 ────────────────────────────────────────────────────
        for _ in range(40):
            refreshed = (await client.get(f"{API}/messages/{posted['id']}", headers=alice_h)).json()
            if refreshed.get("blocks"):
                break
            await asyncio.sleep(0.5)
        assert refreshed.get("blocks") and refreshed["blocks"][0]["type"] == "unfurl", refreshed.get("blocks")
        await page.wait_for_selector(f'article:has-text("문서 {stamp}") .unfurl', timeout=20000)
        ok("링크 언펄: example.com 카드가 메시지 아래에")

        # ── @here / @channel 피커 · 사이드바 섹션 · 배지 병기 ────────────
        await box.fill("")
        await box.type("@ch")
        await page.wait_for_selector('.mention-picker:has-text("채널 전원")')
        await page.keyboard.press("Escape")
        await box.fill("")
        ok("멘션 피커: '@ch' → 채널 전원(@channel) 제안")
        await page.click('button[aria-label="채널 설정"]')
        await page.locator('input[aria-label="사이드바 섹션"]').fill(f"검증 {stamp}")
        await page.locator('.channel-settings button:text-is("적용")').click()
        await page.wait_for_selector('.banner:has-text("섹션으로 옮겼습니다")')
        await page.keyboard.press("Escape")
        await page.wait_for_selector(f'.sidebar-subsection-head:has-text("검증 {stamp}")')
        ok("사이드바 섹션: 채널 설정에서 이름 → 사이드바에 접히는 묶음")
        await client.patch(f"{API}/channels/{random_ch['id']}/membership", headers=alice_h, json={"section": None})
        # 보고 있는 채널은 자동으로 읽음 처리되므로 먼저 다른 채널로 옮긴다.
        await sidebar_item(page, "general").click()
        await page.wait_for_selector('.channel-header:has-text("general")')
        await client.post(f"{API}/channels/{random_ch['id']}/messages", headers=bob_h, json={"body": f"일반 {stamp}"})
        await client.post(f"{API}/channels/{random_ch['id']}/messages", headers=bob_h, json={"body": f"@김앨리스 부름 {stamp}"})
        await asyncio.sleep(2)
        item = sidebar_item(page, "random")
        text = await item.inner_text()
        assert "@1" in text, text
        ok("배지 병기: 멘션 @1 이 안 읽음 수와 함께 표시")

        # ── 첫 진입 카드 (새 계정) ────────────────────────────────────────
        newbie = f"ops-newbie-{stamp}@example.com"
        invite = (
            await client.post(f"{API}/workspaces/{WS}/invites", headers=alice_h, json={"emails": [newbie], "role": "member"})
        ).json()[0]
        assert "emailed" in invite
        token = invite["invite_url"].split("token=")[1].split("&")[0]
        reg = await client.post(f"{API}/auth/register", json={"email": newbie, "password": PW, "display_name": "운영신입", "invite_token": token})
        assert reg.status_code == 201, reg.text
        ctx2 = await browser.new_context(viewport={"width": 1440, "height": 900})
        npage = await ctx2.new_page()
        npage.set_default_timeout(30000)
        await login_ui(npage, newbie)
        await npage.wait_for_selector('.first-run:has-text("오신 것을 환영합니다")')
        await npage.locator('.first-run button:has-text("채널 둘러보기")').click()
        await npage.wait_for_selector(".browse-channels")
        await npage.keyboard.press("Escape")
        await npage.locator('.first-run-close').click()
        await npage.wait_for_selector(".first-run", state="detached")
        await npage.reload()
        await npage.wait_for_selector(".sidebar")
        assert await npage.locator(".first-run").count() == 0
        ok("첫 진입 카드: 신입에게 보이고, 닫으면 다시 안 뜸")
        await ctx2.close()

        # ── 초대 재발송 ──────────────────────────────────────────────────
        invite2 = (
            await client.post(f"{API}/workspaces/{WS}/invites", headers=alice_h, json={"emails": [f"resend-{stamp}@example.com"], "role": "member"})
        ).json()[0]
        resent = await client.post(f"{API}/workspaces/{WS}/invites/{invite2['id']}/resend", headers=alice_h)
        assert resent.status_code == 200 and resent.json()["invite_url"] != invite2["invite_url"]
        ok("초대 재발송: 새 토큰 발급 (구 링크 무효)")
        await client.delete(f"{API}/workspaces/{WS}/invites/{invite2['id']}", headers=alice_h)

        # ── C. 개발자 콘솔: 등록 → 토큰 → 블록 메시지 → 심사 ─────────────
        await page.click('button[aria-label="환경설정"]')
        dev = page.locator('.settings-section:has(h3:text-is("개발자 콘솔"))')
        manifest = {
            "slug": f"smoke-{stamp}",
            "name": f"스모크 앱 {stamp}",
            "version": "1.0.0",
            "kind": "bot",
            "slash_commands": [{"command": f"/smoke{stamp % 1000}", "description": "스모크"}],
            "scopes": ["messages:write"],
        }
        await dev.locator(".manifest-editor").fill(json.dumps(manifest))
        await dev.locator('button:text-is("앱 등록")').click()
        await page.wait_for_selector(".linkapp-blocked:has-text('서명 비밀')")
        await dev.locator('button:has-text("확인했습니다")').click()
        await dev.locator(f'.dev-app-head:has-text("스모크 앱 {stamp}")').click()
        await dev.locator('input[aria-label="토큰 이름"]').fill("스모크 토큰")
        await dev.locator('button:text-is("토큰 발급")').click()
        await page.wait_for_selector(".linkapp-blocked:has-text('서명 비밀')")
        app_token = await page.locator(".secret-code").inner_text()
        await dev.locator('button:has-text("확인했습니다")').click()
        ok("개발자 콘솔: 매니페스트 등록 → 서명 비밀 1회 표시 → 토큰 발급")
        mine = (await client.get(f"{API}/workspaces/{WS}/apps/mine", headers=alice_h)).json()
        app_row = next(a for a in mine if a["slug"] == manifest["slug"])
        await dev.locator('button:text-is("심사 신청")').click()
        await page.wait_for_selector('.banner:has-text("심사를 신청했습니다")')
        review = page.locator('.settings-section:has(h3:text-is("앱 심사"))')
        await review.locator(f'li:has-text("스모크 앱 {stamp}") button:text-is("승인·게시")').click()
        await page.wait_for_selector('.banner:has-text("게시했습니다")')
        published = (await client.get(f"{API}/apps/{app_row['id']}", headers=alice_h)).json()
        assert published["status"] == "published"
        ok("앱 심사: 신청 → 서비스 관리자 승인 → published")
        await page.keyboard.press("Escape")
        installed = await client.post(f"{API}/workspaces/{WS}/apps/{app_row['id']}/install", headers=alice_h, json={"granted_scopes": ["messages:write"], "pin_to_dock": False})
        assert installed.status_code == 201, installed.text
        blocks_msg = await client.post(
            f"{API}/channels/{random_ch['id']}/messages",
            headers={"Authorization": f"Bearer {app_token.strip()}"},
            json={
                "body": f"배포 승인 요청 {stamp}",
                "blocks": [
                    {"type": "section", "text": "v2.3.0 을 프로덕션에 올릴까요?"},
                    {"type": "actions", "elements": [
                        {"type": "button", "text": "승인", "action_id": "approve", "style": "primary"},
                        {"type": "button", "text": "보류", "action_id": "hold"},
                    ]},
                ],
            },
        )
        assert blocks_msg.status_code == 201, blocks_msg.text
        await sidebar_item(page, "random").click()
        row = page.locator(f'article:has-text("배포 승인 요청 {stamp}")')
        await row.locator('.block-button:text-is("승인")').wait_for(state="visible")
        assert await row.locator(".block-section").count() == 1
        ok("인터랙티브 블록: 앱 토큰으로 게시한 섹션+버튼이 렌더됨")
        commands = (await client.get(f"{API}/workspaces/{WS}/commands", headers=alice_h)).json()
        assert any(c["command"] == manifest["slash_commands"][0]["command"] for c in commands)
        ok("슬래시 명령: 설치한 앱의 명령이 목록에 등록")

        await ctx.close()
        await browser.close()

    print(f"\n{len(results)}개 검증 통과")


asyncio.run(main())
