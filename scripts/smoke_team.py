"""5인 팀 실사용 시뮬레이션이 찾은 결함의 회귀 스모크 — smoke_flows.py 의 자매편.

리드·프론트·디자이너·데이터·신입 다섯 에이전트가 하루치 업무를 흘려보내며
찾은 것들을 지킵니다: 한글 이름 멘션, 표/제목/체크리스트 렌더, 공유의 원문
링크, 채널 관리자 위임, 참여/권한 시스템 라인, 삭제된 부모의 스레드 도달,
⌘K 정확 일치 우선·하이라이트, 편집 Enter 저장, 로그아웃 후 설정 모달, 채널
둘러보기, '멘션만' 배지 정책, 스레드 답글의 안 읽음 제외, 초대 링크 재접속,
비공개 채널 파일명 격리.

요구사항은 smoke_ui.py 와 동일: 실행 중인 백엔드(make dev)와 웹 모드(make ui),
LLACK_SMOKE_API / LLACK_SMOKE_UI 로 주소 지정, make seed 데이터.
"""

import asyncio
import os
import time

import hashlib

import httpx
from playwright.async_api import async_playwright

API = os.environ.get("LLACK_SMOKE_API", "http://127.0.0.1:8000") + "/api/v1"
UI = os.environ.get("LLACK_SMOKE_UI", "http://127.0.0.1:1420")
PW = "llack-dev-password"
results = []


def ok(name):
    results.append(name)
    print(f"  ✓ {name}")


async def api_login(client, email):
    r = await client.post(f"{API}/auth/login", json={"email": email, "password": PW})
    r.raise_for_status()
    data = r.json()
    return {"Authorization": f"Bearer {data['tokens']['access_token']}"}, data["user"]


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
    async with httpx.AsyncClient(timeout=20) as client, async_playwright() as p:
        alice_h, alice = await api_login(client, "alice@example.com")
        bob_h, bob = await api_login(client, "bob@example.com")
        dave_h, dave = await api_login(client, "dave@example.com")
        workspaces = (await client.get(f"{API}/workspaces", headers=alice_h)).json()
        WS = next(w for w in workspaces if w["slug"] == "acme")["id"]

        # 신입: 초대 링크로 가입한 새 계정 (초대 재접속·스레드 안 읽음 검증용)
        newbie_email = f"team-newbie-{stamp}@example.com"
        invite = (
            await client.post(
                f"{API}/workspaces/{WS}/invites",
                headers=alice_h,
                json={"emails": [newbie_email], "role": "member"},
            )
        ).json()[0]
        INVITE_TOKEN = invite["invite_url"].split("token=")[1].split("&")[0]
        reg = await client.post(
            f"{API}/auth/register",
            json={
                "email": newbie_email,
                "password": PW,
                "display_name": "팀신입",
                "invite_token": INVITE_TOKEN,
            },
        )
        assert reg.status_code == 201, reg.text
        eve_h = {"Authorization": f"Bearer {reg.json()['tokens']['access_token']}"}

        # 준비: 새 공개 채널 (alice + dave), bob/eve 는 밖에
        ch = (
            await client.post(
                f"{API}/workspaces/{WS}/channels",
                headers=alice_h,
                json={"name": f"검증-{stamp}", "member_ids": [dave["id"]]},
            )
        ).json()
        channels = (await client.get(f"{API}/workspaces/{WS}/channels", headers=alice_h)).json()
        deploy = next(c for c in channels if c.get("name") == "배포")
        random_ch = next(c for c in channels if c.get("name") == "random")

        browser = await p.chromium.launch()
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()
        page.set_default_timeout(30000)
        await login_ui(page, "alice@example.com")
        await sidebar_item(page, ch["name"]).click()
        await page.wait_for_selector(".composer textarea")

        # ── 1. 한글 이름 멘션: 피커 유지 + 서버 mentioned_user_ids ──────────
        box = page.locator(".composer textarea")
        await box.click()
        await box.type("@최데")
        await page.wait_for_selector(".mention-picker", state="visible")
        picker_text = await page.locator(".mention-picker").inner_text()
        assert "최데이브" in picker_text, picker_text
        ok("멘션: '@최데' 입력에도 피커가 열리고 최데이브를 제안")
        await box.fill("")
        await box.type(f"@최데이브님 확인 부탁 {stamp}")
        await page.keyboard.press("Escape")
        await page.keyboard.press("Enter")
        await page.wait_for_selector(f'article:has-text("확인 부탁 {stamp}")')
        msgs = (await client.get(f"{API}/channels/{ch['id']}/messages", headers=alice_h)).json()
        posted = next(m for m in msgs["items"] if f"확인 부탁 {stamp}" in m["body"])
        assert posted["mentioned_user_ids"] == [dave["id"]], posted
        assert posted["body"].startswith(f"<@{dave['id']}>님"), posted["body"]
        rendered = await page.locator(f'article:has-text("확인 부탁 {stamp}") .mention').inner_text()
        assert rendered == "@최데이브", rendered
        ok("멘션: '@최데이브님' 이 서버에서 <@id>님 으로 정규화되고 멘션 배지로 렌더")

        # ── 2. 표·제목·번호 목록·체크리스트·코드 복사 버튼 ───────────────
        rich = (
            f"## 지표 스키마 {stamp}\n"
            "| 컬럼 | 타입 |\n|---|---|\n| landing_cta_click | int |\n| dash_v2 | text |\n"
            "1. 첫째\n2. 둘째\n- [ ] 할 일\n- [x] 끝난 일\n```sql\nSELECT 1;\n```"
        )
        await box.fill(rich)
        await page.keyboard.press("Enter")
        art = page.locator(f'article:has-text("지표 스키마 {stamp}")')
        await art.wait_for(state="visible")
        assert await art.locator(".md-table td").count() == 4
        assert await art.locator("h2.md-heading").count() == 1
        assert await art.locator("ol.md-list li").count() == 2
        assert await art.locator(".md-task input[checked]").count() == 1
        assert await art.locator(".code-copy").count() == 1
        assert await art.locator("p:empty").count() == 0, "코드 블록 앞뒤 빈 <p>"
        ok("마크다운: 표 4셀 · h2 · 번호목록 2 · 체크리스트 · 코드 복사 버튼 · 빈 <p> 없음")

        # ── 3. 공유 → 원문 보기 permalink → 스포트라이트 ─────────────────
        target = page.locator(f'article:has-text("확인 부탁 {stamp}")').last
        await target.hover(position={"x": 200, "y": 10})
        await target.locator('button[aria-label="다른 대화로 공유"]').click()
        await page.wait_for_selector(".share-message")
        await page.locator('.share-list button:has-text("random")').first.click()
        await page.click(".share-send")
        await page.wait_for_selector('.banner:has-text("공유했습니다")')
        shared = (await client.get(f"{API}/channels/{random_ch['id']}/messages", headers=alice_h)).json()
        latest = shared["items"][0]["body"]
        assert f"<#{ch['id']}:{posted['id']}>" in latest, latest
        ok("공유: 인용에 <#채널:메시지> 원문 링크가 붙음")
        await sidebar_item(page, "random").click()
        link = page.locator(".message-link").last
        await link.wait_for(state="visible")
        assert "원문 보기" in await link.inner_text()
        await link.click()
        await page.wait_for_selector(".message.is-spotlit", timeout=20000)
        spot = await page.locator(".message.is-spotlit").inner_text()
        assert f"확인 부탁 {stamp}" in spot
        ok("공유: '원문 보기' 클릭 → 원문 채널의 해당 메시지로 점프·스포트라이트")

        # ── 4. 관리자 위임 UI ────────────────────────────────────────────
        await asyncio.sleep(2.6)
        await page.click('button[aria-label="채널 설정"]')
        row = page.locator('.member-list:not(.member-candidates) li:has-text("최데이브")').first
        await row.locator('button:has-text("관리자로")').click()
        await page.wait_for_selector('.banner:has-text("채널 관리자로 지정했습니다")')
        members = (await client.get(f"{API}/channels/{ch['id']}/members", headers=alice_h)).json()
        assert next(m for m in members if m["user"]["id"] == dave["id"])["role"] == "admin"
        ok("채널 관리자 위임: '관리자로' 버튼 → 배너 → API role=admin")
        await page.keyboard.press("Escape")
        sys_line = page.locator('.message-system:has-text("관리자로 지정했습니다")')
        await sys_line.wait_for(state="visible")
        ok("시스템 메시지: 권한 변경이 전사록에 한 줄로 남음")

        # ── 5. 스레드 부모 삭제 → 툼스톤에 답글 버튼 ─────────────────────
        root = (await client.post(f"{API}/channels/{ch['id']}/messages", headers=alice_h, json={"body": f"삭제될 루트 {stamp}"})).json()
        await client.post(f"{API}/channels/{ch['id']}/messages", headers=dave_h, json={"body": "남는 답글", "parent_id": root["id"]})
        await client.delete(f"{API}/messages/{root['id']}", headers=alice_h)
        await page.reload()
        await page.wait_for_selector(".sidebar")
        await sidebar_item(page, ch["name"]).click()
        tomb = page.locator(".message-deleted .thread-summary").last
        await tomb.wait_for(state="visible")
        await tomb.click()
        await page.wait_for_selector('.thread-pane:has-text("남는 답글")')
        ok("스레드: 부모가 삭제돼도 '답글 N개' 로 스레드에 도달")

        # ── 6. ⌘K: 정확 일치 우선 + <mark> 하이라이트 ────────────────────
        await page.keyboard.press("Escape")
        await page.keyboard.press("Control+k")
        await page.locator(".palette input").fill("디자인")
        await page.wait_for_selector(".palette-results button")
        first = await page.locator(".palette-results button .palette-label").first.inner_text()
        assert first.strip() == "디자인", first
        ok("⌘K: '디자인' → 1위가 #디자인 (디자인-리뷰 아님)")
        await page.locator(".palette input").fill("인증 흐름")
        await page.wait_for_selector(".palette-label mark", timeout=15000)
        ok("⌘K: 메시지 결과에 검색어가 <mark> 로 강조")
        await page.keyboard.press("Escape")

        # ── 7. 편집: Enter 로 저장 ───────────────────────────────────────
        mine = page.locator(f'article:has-text("확인 부탁 {stamp}")').last
        await mine.hover(position={"x": 200, "y": 10})
        await mine.locator('button[aria-label="수정"]').click()
        edit_box = mine.locator(".message-edit textarea")
        await edit_box.fill(f"@최데이브 확인 부탁 {stamp} (수정)")
        await page.keyboard.press("Enter")
        await page.wait_for_selector(f'article:has-text("{stamp} (수정)") .message-edited')
        ok("편집: Enter 로 저장, (수정됨) 표시")

        # ── 8. 설정에서 로그아웃 → 재로그인 시 모달이 닫혀 있음 ───────────
        await page.click('button[aria-label="환경설정"]')
        await page.locator('.settings button:has-text("다른 기기 로그아웃")').wait_for(state="visible")
        await page.locator('.settings button:has-text("로그아웃")').last.click()
        await page.wait_for_selector('input[type="email"]', state="visible")
        await page.fill('input[type="email"]', "alice@example.com")
        await page.fill('input[type="password"]', PW)
        await page.click('button[type="submit"]')
        await page.wait_for_selector(".sidebar")
        assert await page.locator(".settings").count() == 0
        ok("설정 모달: 로그아웃 후 재로그인해도 열려 있지 않음 (+ 다른 기기 로그아웃 버튼 존재)")
        await ctx.close()

        # ── 9. bob: 채널 둘러보기 → 참여 → 시스템 메시지, '멘션만' 배지 정책 ─
        await client.patch(f"{API}/channels/{deploy['id']}/membership", headers=bob_h, json={"notification_level": "mentions", "is_muted": False})
        ctx2 = await browser.new_context(viewport={"width": 1440, "height": 900})
        bpage = await ctx2.new_page()
        bpage.set_default_timeout(30000)
        await login_ui(bpage, "bob@example.com")
        assert await sidebar_item(bpage, ch["name"]).count() == 0
        await bpage.click('button[aria-label="채널 둘러보기"]')
        await bpage.wait_for_selector(".browse-channels")
        row = bpage.locator(f'.browse-list li:has-text("{ch["name"]}")')
        await row.wait_for(state="visible")
        await row.locator('button:has-text("참여")').click()
        await bpage.wait_for_selector(f'.channel-header:has-text("{ch["name"]}"), header:has-text("{ch["name"]}")')
        await sidebar_item(bpage, ch["name"]).wait_for(state="visible")
        await bpage.wait_for_selector('.message-system:has-text("이밥 님이 참여했습니다")')
        ok("채널 둘러보기: 목록에서 참여 → 사이드바 등록 → '이밥 님이 참여했습니다' 시스템 라인")

        await client.post(f"{API}/channels/{deploy['id']}/read", headers=bob_h, json={})
        await asyncio.sleep(1)
        await client.post(f"{API}/channels/{deploy['id']}/messages", headers=dave_h, json={"body": f"배포 알림 {stamp}"})
        await asyncio.sleep(2)
        item = sidebar_item(bpage, "배포")
        assert await item.locator(".badge").count() == 0, "멘션만 채널에 일반 메시지 배지"
        assert "is-unread" not in (await item.get_attribute("class") or "")
        ok("알림 '멘션만': 일반 메시지는 배지도 굵기도 없음")
        await client.post(f"{API}/channels/{deploy['id']}/messages", headers=dave_h, json={"body": f"@이밥 롤백 확인 {stamp}"})
        await item.locator(".badge-mention").wait_for(state="visible", timeout=15000)
        ok("알림 '멘션만': 한글 이름 멘션은 배지로 표시")
        await ctx2.close()

        # ── 10. eve: 스레드 답글이 채널 unread 를 올리지 않음 (API) ─────────
        await client.post(f"{API}/channels/{ch['id']}/join", headers=eve_h)
        await client.post(f"{API}/channels/{ch['id']}/read", headers=eve_h, json={})
        root2 = (await client.post(f"{API}/channels/{ch['id']}/messages", headers=alice_h, json={"body": "스레드 루트"})).json()
        await client.post(f"{API}/channels/{ch['id']}/read", headers=eve_h, json={})
        await client.post(f"{API}/channels/{ch['id']}/messages", headers=alice_h, json={"body": "스레드 안에서만", "parent_id": root2["id"]})
        mem = (await client.get(f"{API}/channels/{ch['id']}", headers=eve_h)).json()["membership"]
        assert mem["unread_count"] == 0, mem
        ok("안 읽음: 스레드 답글은 채널 배지를 올리지 않음")

        # ── 11. 기존 구성원이 초대 링크 재접속 → 오류 없음 ─────────────────
        ctx3 = await browser.new_context(viewport={"width": 1440, "height": 900})
        epage = await ctx3.new_page()
        epage.set_default_timeout(30000)
        await login_ui(epage, newbie_email)
        await epage.goto(f"{UI}/?invite={INVITE_TOKEN}")
        await epage.wait_for_selector(".sidebar")
        await asyncio.sleep(2)
        assert await epage.locator(".banner-error").count() == 0, await epage.locator(".banner").all_inner_texts()
        ok("초대 링크 재접속: 이미 구성원이면 오류 배너 없음")

        # ── 12. 비공개 파일명 검색 격리 (API) ──────────────────────────────
        private = (await client.post(f"{API}/workspaces/{WS}/channels", headers=alice_h, json={"name": f"비밀-{stamp}", "kind": "private"})).json()
        content = b"secret,1\n"
        ticket = (await client.post(f"{API}/workspaces/{WS}/files", headers=alice_h, json={"filename": f"기밀-{stamp}.csv", "mime_type": "text/csv", "size_bytes": len(content), "checksum_sha256": hashlib.sha256(content).hexdigest()})).json()
        await client.put(f"{API}{ticket['upload_url'].removeprefix('/api/v1')}", headers={**alice_h, "Content-Type": "text/csv"}, content=content)
        await client.post(f"{API}/channels/{private['id']}/messages", headers=alice_h, json={"body": "첨부", "file_ids": [ticket["file_id"]]})
        seen = (await client.get(f"{API}/workspaces/{WS}/search?q=기밀-{stamp}", headers=bob_h)).json()
        assert seen["files"] == [], seen["files"]
        ok("비공개 채널 첨부 파일명: 비구성원 검색에 노출되지 않음")

        await ctx3.close()
        await browser.close()

    print(f"\n{len(results)}개 검증 통과")


asyncio.run(main())
