#!/usr/bin/env node
/**
 * 데스크톱 앱을 띄우거나 빌드합니다 — `tauri dev` / `tauri build` 를 대신합니다.
 *
 * 서버 주소는 배포한 뒤에 고정됩니다. 그래서 빌드할 때 정합니다.
 * `LLACK_SERVER_URL` 하나가 그 주소의 출처이고, 여기서 세 곳에 나누어 줍니다.
 *
 *   · 프런트엔드 번들 — API 주소 (vite.config.ts 가 읽습니다)
 *   · Tauri CSP       — 그 주소로의 요청과 이미지를 허용합니다
 *   · Rust 셸         — 알림 제목에 붙일 채널 이름을 물을 때 쓰는 주소
 *
 * 쓰기:
 *   node scripts/tauri.mjs dev
 *   node scripts/tauri.mjs build
 *   node scripts/tauri.mjs build -- --bundles msi
 */
import { spawn } from "node:child_process";

const serverUrl = process.env.LLACK_SERVER_URL ?? "http://127.0.0.1:8000";
const args = process.argv.slice(2);

/** 그 주소에서 갈 수 있는 오리진들 — 개발 중에는 127.0.0.1 과 localhost 가 같은 서버다. */
function origins() {
  const url = new URL(serverUrl);
  const list = [url.origin];
  if (url.hostname === "127.0.0.1" || url.hostname === "localhost") {
    const other = url.hostname === "127.0.0.1" ? "localhost" : "127.0.0.1";
    list.push(`${url.protocol}//${other}${url.port ? `:${url.port}` : ""}`);
  }
  return list;
}

const httpOrigins = origins();
const wsOrigins = httpOrigins.map((origin) => origin.replace(/^http/, "ws"));

/**
 * 콘텐츠 보안 정책 — 앱이 갈 수 있는 곳을 정확히 적습니다.
 *
 * 이 창은 그 주소의 서버와만 이야기합니다. 그래서 그 주소와 그 주소의
 * 실시간 소켓, 그리고 같은 주소에서 오는 파일 이미지만 열어 둡니다.
 */
const csp = {
  "default-src": "'self'",
  "script-src": "'self'",
  "style-src": "'self' 'unsafe-inline'",
  "font-src": "'self' data:",
  "img-src": `'self' data: blob: asset: http://asset.localhost ${httpOrigins.join(" ")}`,
  "media-src": "'self' blob: asset: http://asset.localhost",
  "connect-src": `'self' ipc: http://ipc.localhost ${httpOrigins.join(" ")} ${wsOrigins.join(" ")}`,
  "frame-src": "'self'",
  "object-src": "'none'",
  "base-uri": "'self'",
  "form-action": "'none'",
};

const env = {
  ...process.env,
  LLACK_SERVER_URL: serverUrl,
  // 프런트엔드가 읽는 이름도 같은 값으로 맞춰 넣습니다 — 둘이 어긋나면
  // 화면은 한 주소를 보고 CSP 는 다른 주소를 허용합니다.
  VITE_API_BASE: serverUrl,
  // Tauri 빌드가 이 값을 설정 파일에 합칩니다(json merge patch) — CSP 의
  // connect-src 과 img-src 만 그 주소로 바뀝니다.
  TAURI_CONFIG: JSON.stringify({ app: { security: { csp } } }),
};

const binary = process.platform === "win32" ? "tauri.cmd" : "tauri";
const child = spawn(binary, args, { stdio: "inherit", env });

child.on("exit", (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  else process.exit(code ?? 1);
});
