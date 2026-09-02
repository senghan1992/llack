/**
 * The demo build: the whole app as one static file.
 *
 * Differences from `vite.config.ts`, and why each is needed to end up with a
 * single HTML file that works from any origin:
 *
 * - `__LLACK_DEMO__` flips `src/lib/demo` on, so `web.ts` answers from memory
 *   instead of calling a backend.
 * - `format: "iife"` + `inlineDynamicImports` collapses everything into one
 *   script. A module graph would need `<script type="module">` and separate
 *   files, and the lazily-imported Anthropic SDK would 404.
 * - `assetsInlineLimit: Infinity` turns the 2MB variable font into a data URI
 *   inside the CSS, so the page carries its own typeface.
 * - `cssCodeSplit: false` leaves exactly one stylesheet to inline.
 */

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  define: { __LLACK_DEMO__: "true" },
  build: {
    target: "es2021",
    minify: "esbuild",
    sourcemap: false,
    outDir: "dist-demo",
    cssCodeSplit: false,
    assetsInlineLimit: Number.MAX_SAFE_INTEGER,
    rollupOptions: {
      output: {
        format: "iife",
        inlineDynamicImports: true,
        entryFileNames: "demo.js",
        assetFileNames: "demo.[ext]",
      },
    },
  },
  resolve: {
    alias: { "@": new URL("./src", import.meta.url).pathname },
  },
});
