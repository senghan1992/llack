import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Vite's config runs in Node, but the project does not depend on @types/node
// for a handful of env reads.
declare const process: { env: Record<string, string | undefined> };

/**
 * `LLACK_WEB_HOST` / `LLACK_WEB_PORT` widen the dev server's binding so the UI
 * can be reached from another machine (an SSH tunnel, or a LAN address).
 * Default stays loopback: Tauri is the usual consumer.
 */
const host = process.env.LLACK_WEB_HOST ?? "127.0.0.1";
const port = Number(process.env.LLACK_WEB_PORT ?? 1420);
const backend = process.env.LLACK_BACKEND_URL ?? "http://127.0.0.1:8000";

// Vite serves loopback and bare IPs unconditionally but rejects unknown
// hostnames, which bites when the page is reached through a DNS name.
const allowedHosts = (process.env.LLACK_WEB_ALLOWED_HOSTS ?? "")
  .split(",")
  .map((entry) => entry.trim())
  .filter(Boolean);

// Tauri serves the dev build from a fixed port and needs a predictable host.
export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: {
    port,
    strictPort: true,
    host,
    ...(allowedHosts.length > 0 ? { allowedHosts } : {}),
    // Same-origin API in browser mode: the adapter in `src/lib/web.ts` calls
    // `/api/v1/...` on the page's own origin, so there is no CORS to configure
    // and the WebSocket rides the same tunnel as the page.
    proxy: {
      "/api": { target: backend, changeOrigin: true, ws: true },
    },
    watch: {
      // src-tauri is Rust; cargo watches it, vite should not.
      ignored: ["**/src-tauri/**", "**/core/**", "**/target/**"],
    },
  },
  build: {
    // Match the oldest webview Tauri targets.
    target: "es2021",
    minify: "esbuild",
    sourcemap: false,
    outDir: "dist",
  },
  resolve: {
    alias: { "@": new URL("./src", import.meta.url).pathname },
  },
});
