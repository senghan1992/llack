/**
 * Fold the demo build into one HTML file.
 *
 * Done with a script rather than `vite-plugin-singlefile` so the demo does not
 * add a dependency to the product's `package.json` for a preview artifact.
 * The work is small: Vite has already been told to emit exactly one script and
 * one stylesheet with the font inlined, so this only has to substitute them in
 * and drop the tags that referenced them.
 *
 * The output is written for a host that supplies its own document skeleton (an
 * artifact page), so no `<!doctype>`, `<html>`, `<head>` or `<body>` is
 * emitted — just the title, the style, the mount point and the script.
 */

import { readFile, writeFile, stat } from "node:fs/promises";
import { join } from "node:path";

const dir = "dist-demo";
const [css, js] = await Promise.all([
  readFile(join(dir, "demo.css"), "utf8"),
  readFile(join(dir, "demo.js"), "utf8"),
]);

// `</script>` inside a string literal would end the inline script early. The
// bundle is minified JS, so this is a real hazard, not a theoretical one.
const safeJs = js.replace(/<\/script/gi, "<\\/script");

// The product's own name, nothing appended. This page *is* Llack; "데모" would
// be a page-type label, and the artifact's own description says that already.
const html = `<title>Llack</title>
<style>
${css}
</style>
<div id="root"></div>
<script>
${safeJs}
</script>
`;

const out = "demo.html";
await writeFile(out, html, "utf8");
const { size } = await stat(out);
console.log(`${out}  ${(size / 1024 / 1024).toFixed(2)} MB`);
