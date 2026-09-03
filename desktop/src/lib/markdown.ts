/**
 * Message rendering.
 *
 * Messages are Markdown authored by other people, so this never produces raw
 * HTML from user input: everything is escaped first, then a deliberately small
 * set of constructs is turned into tags. That is the whole reason for
 * hand-rolling it rather than pulling in a Markdown library plus a sanitiser —
 * the escape happens before any tag exists, so there is no sanitisation gap.
 *
 * Supported: fenced code (with a copy button), inline code, bold, italic,
 * strikethrough, blockquote, links (http/https only), `<@user>` mentions,
 * `<#channel>` links, `<#channel:message>` permalinks, headings, bullet and
 * numbered lists, `- [ ]` task lists, pipe tables.
 */

import { replaceShortcodes } from "@/lib/emoji";

export interface RenderContext {
  /** Resolves a user id to a display name for `<@id>` mentions. */
  userName: (id: string) => string | undefined;
  /** Resolves a channel id to a name for `<#id>` links. */
  channelName: (id: string) => string | undefined;
  /** The viewer, so mentions of them can be highlighted differently. */
  viewerId?: string;
}

const ULID = "[0-9A-HJKMNP-TV-Z]{26}";

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
  /** Block-level fragments must not be wrapped in `<p>` — a `<pre>` inside a
   *  `<p>` makes the browser close the paragraph early and leave an empty
   *  `<p></p>` (visible as a blank line above every code block). */
  block: boolean;
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

const TABLE_ROW = /^\s*\|.*\|\s*$/;
const TABLE_RULE = /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$/;

function splitTableRow(line: string): string[] {
  const trimmed = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  return trimmed.split("|").map((cell) => cell.trim());
}

export function renderMessage(body: string, context: RenderContext): string {
  if (!body) return "";

  const placeholders: Placeholder[] = [];
  const stash = (html: string, block = false): string => {
    const token = placeholderToken(placeholders.length);
    placeholders.push({ token, html, block });
    return token;
  };

  // 1. Escape everything up front. Every branch below only ever inserts tags
  //    around already-escaped text.
  let working = escapeHtml(body);

  // 2. Fenced code blocks, stashed so no inline rule touches their contents.
  //    The copy button is real HTML; MessageRow's click handler does the copy.
  working = working.replace(
    /```([a-zA-Z0-9_+-]*)\n?([\s\S]*?)```/g,
    (_match, language: string, code: string) =>
      stash(
        `<div class="code-wrap"><button type="button" class="code-copy" aria-label="코드 복사">복사</button><pre class="code-block"${
          language ? ` data-language="${escapeHtml(language)}"` : ""
        }><code>${code.replace(/\n$/, "")}</code></pre></div>`,
        true,
      ),
  );

  // 3. Inline code, likewise stashed.
  working = working.replace(/`([^`\n]+)`/g, (_match, code: string) =>
    stash(`<code class="code-inline">${code}</code>`),
  );

  // 3b. `:tada:` → 🎉. Code spans are already stashed, so a shortcode inside
  //     backticks stays literal — the same rule mentions follow.
  working = replaceShortcodes(working);

  // 4. Mentions. `&lt;@id&gt;` because the source was escaped in step 1.
  working = working.replace(new RegExp(`&lt;@(${ULID})&gt;`, "g"), (_match, id: string) => {
    const name = context.userName(id);
    const isViewer = context.viewerId === id;
    return stash(
      `<span class="mention${isViewer ? " mention-me" : ""}" data-user-id="${id}">@${
        name ? escapeHtml(name) : "알 수 없는 사용자"
      }</span>`,
    );
  });

  // 5. Channel-wide mentions.
  working = working.replace(
    /(?<![\w])@(here|channel|everyone)\b/g,
    (_match, keyword: string) =>
      stash(`<span class="mention mention-broadcast">@${keyword}</span>`),
  );

  // 6a. Message permalinks `<#channel:message>` — a share's "see the original".
  working = working.replace(
    new RegExp(`&lt;#(${ULID}):(${ULID})&gt;`, "g"),
    (_match, channelId: string, messageId: string) => {
      const name = context.channelName(channelId);
      return stash(
        `<a class="channel-link message-link" href="#" data-channel-id="${channelId}" data-message-id="${messageId}">#${
          name ? escapeHtml(name) : "채널"
        } · 원문 보기</a>`,
      );
    },
  );

  // 6b. Channel links.
  working = working.replace(new RegExp(`&lt;#(${ULID})&gt;`, "g"), (_match, id: string) => {
    const name = context.channelName(id);
    return stash(
      `<a class="channel-link" href="#" data-channel-id="${id}">#${
        name ? escapeHtml(name) : "채널"
      }</a>`,
    );
  });

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
  let list: "ul" | "ol" | null = null;
  const blockTokens = new Set(placeholders.filter((p) => p.block).map((p) => p.token));

  const closeList = () => {
    if (list) {
      output.push(`</${list}>`);
      list = null;
    }
  };
  const openList = (kind: "ul" | "ol") => {
    if (list !== kind) {
      closeList();
      output.push(`<${kind} class="md-list">`);
      list = kind;
    }
  };
  const listItem = (content: string): string => {
    const task = /^\[( |x|X)\]\s+(.*)$/.exec(content);
    if (task) {
      const checked = task[1] !== " ";
      return `<li class="md-task${checked ? " is-done" : ""}"><input type="checkbox" disabled${
        checked ? " checked" : ""
      } /> <span>${task[2] ?? ""}</span></li>`;
    }
    return `<li>${content}</li>`;
  };

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index] ?? "";

    // Pipe table: a header row followed by a `|---|---|` rule.
    const next = lines[index + 1];
    if (TABLE_ROW.test(line) && next !== undefined && TABLE_RULE.test(next)) {
      closeList();
      const header = splitTableRow(line);
      const rows: string[][] = [];
      let cursor = index + 2;
      while (cursor < lines.length && TABLE_ROW.test(lines[cursor] ?? "")) {
        rows.push(splitTableRow(lines[cursor] ?? ""));
        cursor += 1;
      }
      output.push(
        `<div class="md-table-wrap"><table class="md-table"><thead><tr>${header
          .map((cell) => `<th>${cell}</th>`)
          .join("")}</tr></thead><tbody>${rows
          .map(
            (row) =>
              `<tr>${header.map((_h, i) => `<td>${row[i] ?? ""}</td>`).join("")}</tr>`,
          )
          .join("")}</tbody></table></div>`,
      );
      index = cursor - 1;
      continue;
    }

    const bullet = /^\s*[-*+]\s+(.*)$/.exec(line);
    if (bullet) {
      openList("ul");
      output.push(listItem(bullet[1] ?? ""));
      continue;
    }
    const numbered = /^\s*\d{1,3}[.)]\s+(.*)$/.exec(line);
    if (numbered) {
      openList("ol");
      output.push(listItem(numbered[1] ?? ""));
      continue;
    }
    closeList();

    const heading = /^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$/.exec(line);
    if (heading) {
      const level = Math.min(4, (heading[1] ?? "#").length);
      output.push(`<h${level} class="md-heading">${heading[2] ?? ""}</h${level}>`);
      continue;
    }

    const quote = /^\s*&gt;\s?(.*)$/.exec(line);
    if (quote) {
      output.push(`<blockquote>${quote[1] ?? ""}</blockquote>`);
      continue;
    }

    const trimmed = line.trim();
    if (trimmed === "") {
      output.push("<br/>");
    } else if (blockTokens.has(trimmed)) {
      // A code block on its own line stands alone — no paragraph around it.
      output.push(trimmed);
    } else {
      output.push(`<p>${line}</p>`);
    }
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
  let text = replaceShortcodes(body)
    .replace(/```[\s\S]*?```/g, "[코드]")
    .replace(/`([^`\n]+)`/g, "$1")
    .replace(
      new RegExp(`<@(${ULID})>`, "g"),
      (_m, id: string) => `@${context.userName(id) ?? "사용자"}`,
    )
    .replace(
      new RegExp(`<#(${ULID})(?::${ULID})?>`, "g"),
      (_m, id: string) => `#${context.channelName(id) ?? "채널"}`,
    )
    .replace(/!\[[^\]]*\]\([^)]*\)/g, "[이미지]")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    // Strip Markdown *markers*, not characters: `landing_cta_click` and
    // `9/13~9/15` must survive. Table rules and pipes go, cells stay.
    .replace(/\*\*|__|~~|\*/g, "")
    .replace(/(?<!\w)_([^_\n]+)_(?!\w)/g, "$1")
    .replace(/^\s{0,3}#{1,6}\s+/gm, "")
    .replace(/^\s*>\s?/gm, "")
    .replace(/^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$/gm, "")
    .replace(/\|/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (text.length > limit) text = `${text.slice(0, limit)}…`;
  return text;
}

/** `@` followed by anything up to whitespace or punctuation: the token a
 *  person types when they write a name the way the UI shows it. */
const NAME_TOKEN = /(?<![\w<@])@([^\s@<>`*_~,.!?;:()[\]{}"'…/\\]{1,64})/g;

/**
 * Turn `@handle` — and `@표시이름` — typed in the composer into the canonical
 * `<@id>` form.
 *
 * `nameToId` maps lower-cased display names to ids and should only contain
 * names that are unique in the workspace; an ambiguous name mentions nobody
 * rather than the wrong person. Longest name wins, so `@김앨리스님` resolves
 * 김앨리스 and keeps the 님.
 */
export function canonicaliseMentions(
  body: string,
  handleToId: Map<string, string>,
  nameToId: Map<string, string> = new Map(),
): string {
  if (handleToId.size === 0 && nameToId.size === 0) return body;

  // Protect code spans so a handle written inside backticks is left alone —
  // the same rule the server applies.
  const codeSpans: string[] = [];
  const stashed = body.replace(/```[\s\S]*?```|`[^`\n]+`/g, (match) => {
    codeSpans.push(match);
    return `<llack-code:${codeSpans.length - 1}>`;
  });
  let rewritten = stashed.replace(
    /(?<![\w<])@([a-z0-9][a-z0-9._-]{1,63})\b/gi,
    (match, handle: string) => {
      const id = handleToId.get(handle.toLowerCase());
      return id ? `<@${id}>` : match;
    },
  );
  if (nameToId.size > 0) {
    const names = [...nameToId.keys()].sort((a, b) => b.length - a.length);
    rewritten = rewritten.replace(NAME_TOKEN, (match, token: string) => {
      // ASCII tokens were the handle path's business above.
      // eslint-disable-next-line no-control-regex
      if (/^[\x00-\x7f]*$/.test(token)) return match;
      const lowered = token.toLowerCase();
      for (const name of names) {
        if (lowered.startsWith(name)) {
          return `<@${nameToId.get(name)}>${token.slice(name.length)}`;
        }
      }
      return match;
    });
  }
  return rewritten.replace(
    /<llack-code:(\d+)>/g,
    (_m, index: string) => codeSpans[Number(index)] ?? "",
  );
}

/** Lower-cased display name → id, for names that are unique in the workspace. */
export function uniqueNameMap(people: Iterable<{ id: string; display_name: string }>): Map<string, string> {
  const counts = new Map<string, number>();
  const ids = new Map<string, string>();
  for (const person of people) {
    const key = person.display_name.trim().toLowerCase();
    if (!key) continue;
    counts.set(key, (counts.get(key) ?? 0) + 1);
    ids.set(key, person.id);
  }
  for (const [key, count] of counts) {
    if (count > 1) ids.delete(key);
  }
  return ids;
}
