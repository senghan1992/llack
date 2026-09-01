/**
 * Message rendering.
 *
 * Messages are Markdown authored by other people, so this never produces raw
 * HTML from user input: everything is escaped first, then a deliberately small
 * set of constructs is turned into tags. That is the whole reason for
 * hand-rolling it rather than pulling in a Markdown library plus a sanitiser —
 * the escape happens before any tag exists, so there is no sanitisation gap.
 *
 * Supported: fenced code, inline code, bold, italic, strikethrough,
 * blockquote, links (http/https only), `<@user>` mentions, `<#channel>` links,
 * bullet lists.
 */

export interface RenderContext {
  /** Resolves a user id to a display name for `<@id>` mentions. */
  userName: (id: string) => string | undefined;
  /** Resolves a channel id to a name for `<#id>` links. */
  channelName: (id: string) => string | undefined;
  /** The viewer, so mentions of them can be highlighted differently. */
  viewerId?: string;
}

export function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/** Only http(s) links become anchors; anything else stays literal text. */
function safeUrl(url: string): string | null {
  try {
    const parsed = new URL(url);
    if (parsed.protocol === "http:" || parsed.protocol === "https:") {
      return parsed.toString();
    }
    return null;
  } catch {
    return null;
  }
}

interface Placeholder {
  token: string;
  html: string;
}

/**
 * Placeholder token for a fragment that must not be touched by later rules.
 *
 * Raw angle brackets are safe as a sentinel precisely because escaping runs
 * first: after `escapeHtml`, no `<` from user input survives, so a token of
 * this shape cannot be forged by whoever wrote the message.
 */
function placeholderToken(index: number): string {
  return `<llack-ph:${index}>`;
}

export function renderMessage(body: string, context: RenderContext): string {
  if (!body) return "";

  const placeholders: Placeholder[] = [];
  const stash = (html: string): string => {
    const token = placeholderToken(placeholders.length);
    placeholders.push({ token, html });
    return token;
  };

  // 1. Escape everything up front. Every branch below only ever inserts tags
  //    around already-escaped text.
  let working = escapeHtml(body);

  // 2. Fenced code blocks, stashed so no inline rule touches their contents.
  working = working.replace(
    /```([a-zA-Z0-9_+-]*)\n?([\s\S]*?)```/g,
    (_match, language: string, code: string) =>
      stash(
        `<pre class="code-block"${
          language ? ` data-language="${escapeHtml(language)}"` : ""
        }><code>${code.replace(/\n$/, "")}</code></pre>`,
      ),
  );

  // 3. Inline code, likewise stashed.
  working = working.replace(/`([^`\n]+)`/g, (_match, code: string) =>
    stash(`<code class="code-inline">${code}</code>`),
  );

  // 4. Mentions. `&lt;@id&gt;` because the source was escaped in step 1.
  working = working.replace(
    /&lt;@([0-9A-HJKMNP-TV-Z]{26})&gt;/g,
    (_match, id: string) => {
      const name = context.userName(id);
      const isViewer = context.viewerId === id;
      return stash(
        `<span class="mention${isViewer ? " mention-me" : ""}" data-user-id="${id}">@${
          name ? escapeHtml(name) : "알 수 없는 사용자"
        }</span>`,
      );
    },
  );

  // 5. Channel-wide mentions.
  working = working.replace(
    /(?<![\w])@(here|channel|everyone)\b/g,
    (_match, keyword: string) =>
      stash(`<span class="mention mention-broadcast">@${keyword}</span>`),
  );

  // 6. Channel links.
  working = working.replace(
    /&lt;#([0-9A-HJKMNP-TV-Z]{26})&gt;/g,
    (_match, id: string) => {
      const name = context.channelName(id);
      return stash(
        `<a class="channel-link" href="#" data-channel-id="${id}">#${
          name ? escapeHtml(name) : "채널"
        }</a>`,
      );
    },
  );

  // 7. Markdown links, then bare URLs.
  working = working.replace(
    /\[([^\]]+)\]\(([^)\s]+)\)/g,
    (match, label: string, url: string) => {
      const href = safeUrl(unescapeForUrl(url));
      if (!href) return match;
      return stash(
        `<a class="link" href="${escapeHtml(
          href,
        )}" target="_blank" rel="noreferrer noopener">${label}</a>`,
      );
    },
  );
  working = working.replace(/(?<![">=])\bhttps?:\/\/[^\s<]+/g, (match) => {
    const href = safeUrl(unescapeForUrl(match));
    if (!href) return match;
    return stash(
      `<a class="link" href="${escapeHtml(
        href,
      )}" target="_blank" rel="noreferrer noopener">${escapeHtml(collapse(href))}</a>`,
    );
  });

  // 8. Emphasis. Applied after links so a URL containing `_` is unaffected.
  working = working.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
  working = working.replace(/(?<![*\w])\*([^*\n]+)\*(?!\w)/g, "<em>$1</em>");
  working = working.replace(/(?<![~\w])~~([^~\n]+)~~/g, "<del>$1</del>");

  // 9. Block constructs, line by line.
  const lines = working.split("\n");
  const output: string[] = [];
  let inList = false;

  const closeList = () => {
    if (inList) {
      output.push("</ul>");
      inList = false;
    }
  };

  for (const line of lines) {
    const bullet = /^\s*[-*+]\s+(.*)$/.exec(line);
    if (bullet) {
      if (!inList) {
        output.push('<ul class="md-list">');
        inList = true;
      }
      output.push(`<li>${bullet[1] ?? ""}</li>`);
      continue;
    }
    closeList();

    const quote = /^\s*&gt;\s?(.*)$/.exec(line);
    if (quote) {
      output.push(`<blockquote>${quote[1] ?? ""}</blockquote>`);
      continue;
    }

    output.push(line.trim() === "" ? "<br/>" : `<p>${line}</p>`);
  }
  closeList();

  let html = output.join("");

  // 10. Restore the stashed fragments.
  for (const { token, html: fragment } of placeholders) {
    html = html.split(token).join(fragment);
  }
  return html;
}

/** Undo the HTML escaping applied in step 1, for URL parsing only. */
function unescapeForUrl(url: string): string {
  return url
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">");
}

function collapse(url: string, max = 60): string {
  return url.length <= max ? url : `${url.slice(0, max - 1)}…`;
}

/**
 * Plain-text preview for the sidebar and notification bodies.
 * Mentions become readable names rather than raw ids.
 */
export function previewText(
  body: string,
  context: RenderContext,
  limit = 90,
): string {
  let text = body
    .replace(/```[\s\S]*?```/g, "[코드]")
    .replace(/`([^`\n]+)`/g, "$1")
    .replace(
      /<@([0-9A-HJKMNP-TV-Z]{26})>/g,
      (_m, id: string) => `@${context.userName(id) ?? "사용자"}`,
    )
    .replace(
      /<#([0-9A-HJKMNP-TV-Z]{26})>/g,
      (_m, id: string) => `#${context.channelName(id) ?? "채널"}`,
    )
    .replace(/!\[[^\]]*\]\([^)]*\)/g, "[이미지]")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/[*_~>#|]+/g, "")
    .replace(/\s+/g, " ")
    .trim();
  if (text.length > limit) text = `${text.slice(0, limit)}…`;
  return text;
}

/** Turn `@handle` typed in the composer into the canonical `<@id>` form. */
export function canonicaliseMentions(
  body: string,
  handleToId: Map<string, string>,
): string {
  if (handleToId.size === 0) return body;

  // Protect code spans so a handle written inside backticks is left alone —
  // the same rule the server applies.
  const codeSpans: string[] = [];
  const stashed = body.replace(/```[\s\S]*?```|`[^`\n]+`/g, (match) => {
    codeSpans.push(match);
    return `<llack-code:${codeSpans.length - 1}>`;
  });
  const rewritten = stashed.replace(
    /(?<![\w<])@([a-z0-9][a-z0-9._-]{1,63})\b/gi,
    (match, handle: string) => {
      const id = handleToId.get(handle.toLowerCase());
      return id ? `<@${id}>` : match;
    },
  );
  return rewritten.replace(
    /<llack-code:(\d+)>/g,
    (_m, index: string) => codeSpans[Number(index)] ?? "",
  );
}
