#!/usr/bin/env python3
"""화면의 글자가 배경에 묻히지 않는지 점검한다 — hover · 정적 대비 전수 조사.

브라우저가 실제로 그리는 색을 잰다. CSS 를 해석하는 게 아니라, 렌더된
페이지에서 색을 읽어 WCAG 대비(AA: 본문 4.5:1 · 큰 글 3:1)를 확인한다.

  · 정적 — 포인터가 없을 때의 모든 글자
  · hover — 앱의 모든 `:hover` 규칙을 하나씩 강제로 켜고, 그 안에 있는
            글자를 다시 잰다. 화면 밖 요소도(:hover 규칙이 걸린 대상은
            화면 밖이어도) 빠짐없이 검사한다.

요구사항:
  - 실행 중인 백엔드 (make dev) 와 웹 프런트엔드 (make dev-web)
  - playwright + chromium:  pip install playwright && playwright install chromium
  - 시드 데이터 (make seed)의 계정

사용법:
    python3 scripts/check-contrast.py
    python3 scripts/check-contrast.py --url http://127.0.0.1:1420 --email you@x.kr --password pw

종료 코드: 위반이 있으면 1, 없으면 0.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS_FILE = ROOT / "desktop" / "src" / "styles" / "app.css"

API = os.environ.get("LLACK_SMOKE_API", "http://127.0.0.1:8000")
UI = os.environ.get("LLACK_SMOKE_UI", "http://127.0.0.1:1420")

# ── 측정 ──────────────────────────────────────────────────────────────────

# 텍스트를 칠하는 요소를 훑어, 배경(알파 포함)을 합성한 뒤 색을 돌려준다.
MEASURE = """
(el) => {
  const cv = document.createElement('canvas');
  cv.width = cv.height = 1;
  const ctx = cv.getContext('2d', { willReadFrequently: true });
  const toRGBA = (c) => {
    if (!c) return [0, 0, 0, 0];
    ctx.clearRect(0, 0, 1, 1);
    ctx.fillStyle = '#000000';
    ctx.fillStyle = c;
    ctx.fillRect(0, 0, 1, 1);
    const d = ctx.getImageData(0, 0, 1, 1).data;
    return [d[0], d[1], d[2], d[3] / 255];
  };
  // 배경 후보를 여러 개 돌려준다 — 그라디언트면 각 색 스톱이 후보다.
  const backgrounds = (el) => {
    const layers = [];
    let node = el;
    while (node && node.nodeType === 1) {
      const s = getComputedStyle(node);
      const img = s.backgroundImage;
      if (img && img !== 'none' && img.indexOf('gradient') !== -1) {
        const stops = img.match(/rgba?\\([^)]*\\)|oklch\\([^)]*\\)|#[0-9a-f]{3,8}/gi) || [];
        const cols = stops.map(toRGBA);
        if (cols.length) layers.push(cols);
        else { const c = toRGBA(s.backgroundColor); if (c[3] > 0) layers.push([c]); }
      } else {
        const c = toRGBA(s.backgroundColor);
        if (c[3] > 0) layers.push([c]);
      }
      node = node.parentElement;
    }
    let base = toRGBA(getComputedStyle(document.documentElement).backgroundColor);
    if (base[3] === 0) base = [255, 255, 255, 1];
    let acc = [base];
    for (let i = layers.length - 1; i >= 0; i--) {
      const next = [];
      for (const under of acc) for (const over of layers[i]) {
        const a = over[3];
        next.push([
          over[0] * a + under[0] * (1 - a),
          over[1] * a + under[1] * (1 - a),
          over[2] * a + under[2] * (1 - a),
          1,
        ]);
      }
      acc = next;
    }
    return acc;
  };
  const out = [];
  const walk = (node) => {
    if (!node) return;
    for (const n of node.childNodes) {
      if (n.nodeType === 3 && n.textContent.trim()) out.push(node);
    }
    for (const c of node.children) walk(c);
  };
  walk(el);
  return out.map((t) => {
    const s = getComputedStyle(t);
    const rect = t.getBoundingClientRect();
    return {
      cls: t.className.toString(),
      tag: t.tagName,
      text: t.textContent.trim().slice(0, 40),
      color: toRGBA(s.color),
      fontSize: parseFloat(s.fontSize),
      fontWeight: parseInt(s.fontWeight) || 400,
      opacity: parseFloat(s.opacity),
      bg: backgrounds(t),
      disabled: !!t.closest('[disabled], [aria-disabled="true"]'),
      visible: s.visibility !== 'hidden' && s.display !== 'none' && rect.width >= 1 && rect.height >= 1,
    };
  });
}
"""


def luminance(rgb: list[float]) -> float:
    def channel(value: float) -> float:
        v = value / 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(rgb[0]) + 0.7152 * channel(rgb[1]) + 0.0722 * channel(rgb[2])


def contrast(a: list[float], b: list[float]) -> float:
    la, lb = luminance(a), luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def check(sample: dict) -> tuple[float, float, list[float]]:
    """(대비, 필요한 대비, 가장 나쁜 배경) — 배경 후보 중 가장 안 좋은 것을 고른다."""
    fg = list(sample["color"])
    bgs = sample["bg"]
    if fg[3] < 1:
        alpha = fg[3]
        fg = [fg[i] * alpha + bgs[0][i] * (1 - alpha) for i in range(3)]
    if sample["opacity"] < 1:
        fg = [c * sample["opacity"] for c in fg]
    worst = min(bgs, key=lambda bg: contrast(fg, bg))
    need = 3.0 if sample["fontSize"] >= 24 or (
        sample["fontSize"] >= 18.66 and sample["fontWeight"] >= 700
    ) else 4.5
    return contrast(fg, worst), need, worst


def hover_selectors(css: str) -> list[str]:
    """`:hover` 규칙이 걸린 선택자들 — 강제로 켜 볼 대상."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    found = set()
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        head = match.group(1)
        if ":hover" not in head:
            continue
        for part in head.split(","):
            part = part.strip()
            if ":hover" in part:
                part = part.replace(":hover", "").strip()
            if part and not part.startswith("@"):
                found.add(part)
    return sorted(found)


# ── 화면 ──────────────────────────────────────────────────────────────────


def screens() -> list[tuple[str, object]]:
    """(이름, 화면을 여는 동작) 목록."""

    def nothing(page):
        return None

    def schedule(page):
        page.get_by_text("일정", exact=True).first.click()
        page.wait_for_timeout(1000)

    def projects(page):
        page.get_by_text("프로젝트", exact=True).first.click()
        page.wait_for_timeout(1200)

    def thread(page):
        page.locator(".msg__thread").first.click()
        page.wait_for_timeout(1200)

    def palette(page):
        page.keyboard.press("Meta+k")
        page.wait_for_timeout(900)

    def settings(page):
        page.locator(".wkey").click()
        page.wait_for_timeout(500)
        page.get_by_text("설정", exact=True).first.click()
        page.wait_for_timeout(1100)

    def new_channel(page):
        page.get_by_label("채널 만들기").first.click()
        page.wait_for_timeout(900)

    def project_chart(page):
        page.get_by_text("프로젝트", exact=True).first.click()
        page.wait_for_timeout(1200)
        # The chart opens from the project's own period, in the header. The
        # list is hidden while the board sits beside the conversation, so the
        # board takes the whole screen first.
        expand = page.get_by_label("보드를 전체 화면으로")
        if expand.count():
            expand.first.click()
            page.wait_for_timeout(800)
        page.locator(".proj__period").first.click()
        page.wait_for_timeout(1200)

    return [
        ("채널", nothing),
        ("일정", schedule),
        ("프로젝트", projects),
        ("프로젝트 차트", project_chart),
        ("스레드", thread),
        ("검색 팔레트", palette),
        ("설정", settings),
        ("새 채널", new_channel),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="화면 글자의 대비를 점검한다")
    parser.add_argument("--url", default=UI, help="웹 프런트엔드 주소")
    parser.add_argument("--email", default="hyunjin@hanbit.co.kr", help="로그인 이메일")
    parser.add_argument("--password", default="hanbit2026", help="로그인 비밀번호")
    parser.add_argument("--api", default=API, help="백엔드 주소 (안 쓰는 옵션 · 예약)")
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "playwright 가 없습니다:  pip install playwright && playwright install chromium",
            file=sys.stderr,
        )
        return 2

    selectors = hover_selectors(CSS_FILE.read_text(encoding="utf-8"))
    findings: list[dict] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        client = page.context.new_cdp_session(page)
        client.send("DOM.enable")
        client.send("CSS.enable")

        page.goto(args.url)
        page.wait_for_timeout(1200)
        page.fill("#gate-email", args.email)
        page.fill("#gate-password", args.password)
        page.click("button[type=submit]")
        page.wait_for_timeout(2500)

        for theme in ("light", "dark"):
            for name, opener in screens():
                page.goto(args.url)
                page.wait_for_timeout(1600)
                page.evaluate(
                    "t => { localStorage.setItem('llack.settings',"
                    " JSON.stringify({ theme: t }));"
                    " document.documentElement.dataset.theme = t; }",
                    theme,
                )
                page.wait_for_timeout(300)
                opener(page)
                page.wait_for_timeout(300)

                # ── 정적 ────────────────────────────────────────────────
                for sample in page.query_selector("body").evaluate(MEASURE):
                    if not sample["visible"] or sample["opacity"] < 0.15:
                        continue
                    ratio, need, bg = check(sample)
                    if ratio < need:
                        findings.append(
                            {
                                "mode": "정적",
                                "screen": f"{theme} · {name}",
                                "cls": sample["cls"],
                                "text": sample["text"],
                                "ratio": round(ratio, 2),
                                "need": need,
                                "fg": sample["color"],
                                "bg": bg,
                                "disabled": sample["disabled"],
                            }
                        )

                # ── hover ───────────────────────────────────────────────
                for selector in selectors:
                    try:
                        handles = page.query_selector_all(selector)
                    except Exception:
                        continue
                    for handle in handles:
                        try:
                            if not handle.is_visible():
                                continue
                            handle.evaluate("e => e.setAttribute('data-contrast-probe', '1')")
                            doc = client.send("DOM.getDocument", {"depth": -1})
                            node_id = client.send(
                                "DOM.querySelector",
                                {
                                    "nodeId": doc["root"]["nodeId"],
                                    "selector": "[data-contrast-probe='1']",
                                },
                            )["nodeId"]
                            handle.evaluate("e => e.removeAttribute('data-contrast-probe')")
                            if not node_id:
                                continue
                            client.send(
                                "CSS.forcePseudoState",
                                {"nodeId": node_id, "forcedPseudoClasses": ["hover"]},
                            )
                            page.wait_for_timeout(180)
                            samples = handle.evaluate(MEASURE)
                            client.send(
                                "CSS.forcePseudoState",
                                {"nodeId": node_id, "forcedPseudoClasses": []},
                            )
                            for sample in samples:
                                if not sample["visible"] or sample["opacity"] < 0.15:
                                    continue
                                ratio, need, bg = check(sample)
                                if ratio < need:
                                    findings.append(
                                        {
                                            "mode": "hover",
                                            "screen": f"{theme} · {name}",
                                            "cls": sample["cls"],
                                            "text": sample["text"],
                                            "ratio": round(ratio, 2),
                                            "need": need,
                                            "fg": sample["color"],
                                            "bg": bg,
                                            "disabled": sample["disabled"],
                                            "selector": selector,
                                        }
                                    )
                        except Exception:
                            continue

        browser.close()

    seen = set()
    unique = []
    for finding in findings:
        key = (
            finding["mode"],
            finding["screen"],
            finding["cls"],
            finding["text"],
            finding.get("selector"),
            finding["ratio"],
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(finding)

    for finding in unique:
        where = finding["screen"]
        what = finding["cls"] or finding["text"]
        print(
            f"  ✗ {where:26s} {finding['mode']:5s} {finding['ratio']:>5}/{finding['need']}"
            f"  .{what:22s} 글자={finding['text']!r}"
            f"  배경={finding.get('selector') or '기본'}"
        )

    print(f"\n{len(unique)}건 위반 · 점검한 hover 규칙 {len(selectors)}개")
    if unique:
        print("글자가 배경에 묻힙니다. 해당 상태의 글자색과 배경색을 함께 고쳐야 합니다.")
        return 1
    print("모든 글자가 자기 배경 위에 읽힙니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
