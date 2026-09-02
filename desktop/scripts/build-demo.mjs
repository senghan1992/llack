/**
 * Fold the demo build into one HTML file.
 *
 * Done with a script rather than `vite-plugin-singlefile` so the demo does not
 * add a dependency to the product's `package.json` for a preview artifact.
 * The work is small: Vite has already been told to emit exactly one script and
 * one stylesheet with the font inlined, so this only has to substitute them in
 * and drop the tags that referenced them.
 *
 * Two outputs from the same pieces:
 *
 * - `demo.html` — a fragment for a host that supplies its own document
 *   skeleton (an artifact page): no `<!doctype>`, `<html>`, `<head>` or
 *   `<body>`, just the title, the style, the mount point and the script.
 * - `demo-standalone.html` — a complete document for opening straight from
 *   the filesystem. The fragment read over `file://` has no charset header
 *   and no meta to declare one, so the Korean UI renders as mojibake; this
 *   variant exists so nobody has to hand-prepend a `<meta charset>` again.
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

const standalone = `<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Llack</title>
<style>
${css}
</style>
</head>
<body>
<div id="root"></div>
<script>
${safeJs}
</script>
</body>
</html>
`;

for (const [out, body] of [
  ["demo.html", html],
  ["demo-standalone.html", standalone],
]) {
  await writeFile(out, body, "utf8");
  const { size } = await stat(out);
  console.log(`${out}  ${(size / 1024 / 1024).toFixed(2)} MB`);
}
