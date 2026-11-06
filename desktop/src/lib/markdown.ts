/**
 * A deliberately small inline renderer: escapes everything first, then promotes
 * a fixed set of marks. No raw HTML ever reaches the DOM.
 */

const ESCAPES: Record<string, string> = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
};

export function escapeHtml(input: string): string {
  return input.replace(/[&<>"']/g, (ch) => ESCAPES[ch]);
}

function inline(text: string): string {
  return text
    .replace(/`([^`\n]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[\s(])\*([^*\n]+)\*/g, "$1<em>$2</em>")
    .replace(/~~([^~\n]+)~~/g, "<del>$1</del>")
    .replace(
      /(https?:\/\/[^\s<]+[^\s<.,:;"')\]])/g,
      '<a href="$1" target="_blank" rel="noreferrer noopener">$1</a>',
    )
    .replace(/(^|\s)@([\w가-힯][\w가-힯.-]{1,30})/g, '$1<span class="msg__mention">@$2</span>');
}

/** Escaped HTML for a message body, with fenced code blocks preserved. */
export function renderBody(body: string): string {
  const parts = body.split(/```/);
  return parts
    .map((part, index) => {
      if (index % 2 === 1) {
        const code = part.replace(/^[a-zA-Z0-9+#-]*\n/, "");
        return `<pre><code>${escapeHtml(code.replace(/\n$/, ""))}</code></pre>`;
      }
      return inline(escapeHtml(part)).replace(/\n/g, "<br />");
    })
    .join("");
}

const EMOJI = [
  "👍", "👎", "❤️", "🎉", "👀",
  "🔥", "✅", "🙏", "😅", "🤝",
  "💡", "🚀", "🐛", "📌", "☕",
];

export const QUICK_REACTIONS = EMOJI;
