import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/**
 * 이 빌드가 연결할 서버.
 *
 * 배포한 뒤에는 서버 주소가 정해집니다 — 그래서 빌드할 때 정합니다.
 * `LLACK_SERVER_URL` 이 그 주소의 출처입니다 (scripts/tauri.mjs 가 같은
 * 값을 CSP 와 Rust 셸에도 나눠 줍니다).
 *
 * `VITE_API_BASE` 를 직접 주면 그것을 씁니다 — 브라우저로만 띄워 볼 때
 * 주소를 시험하기 편하게 하기 위해서입니다. 앱 빌드에서는
 * scripts/tauri.mjs 가 이 값을 `LLACK_SERVER_URL` 로 맞춰 넣으므로
 * 두 곳이 어긋나지 않습니다.
 */
const serverUrl =
  process.env.VITE_API_BASE ?? process.env.LLACK_SERVER_URL ?? "http://127.0.0.1:8000";

// 앱은 `import.meta.env.VITE_API_BASE` 로 이 주소를 읽습니다. Vite 는
// `VITE_` 로 시작하는 이름만 클라이언트에 노출하므로 그 이름으로 건넵니다.
process.env.VITE_API_BASE = serverUrl;

export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
    host: "127.0.0.1",
    // 개발 중에는 API 를 같은 오리진으로 프록시한다. 브라우저가 어느 주소로
    // 페이지에 들어왔든(localhost 포트 포워딩, 사내 IP, https 프록시) 같은 오리진
    // 으로만 요청하므로 CORS 와 mixed content 문제가 생기지 않는다.
    // ws: true 는 실시간 소켓(/api/v1/ws) 업그레이드도 함께 넘긴다.
    proxy: {
      "/api": {
        target: serverUrl,
        changeOrigin: true,
        ws: true,
      },
    },
  },
  envPrefix: ["VITE_", "TAURI_"],
  build: {
    target: "es2022",
    sourcemap: false,
    chunkSizeWarningLimit: 900,
  },
});
