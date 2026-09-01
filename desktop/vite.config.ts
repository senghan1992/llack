import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Tauri serves the dev build from a fixed port and needs a predictable host.
export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
    host: "127.0.0.1",
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
