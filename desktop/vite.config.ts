import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

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
        target: "http://127.0.0.1:8000",
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
