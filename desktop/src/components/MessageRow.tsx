import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type FocusEvent,
  type MouseEvent,
} from "react";
import { createPortal } from "react-dom";
import {
  Copy,
  CornerUpLeft,
  Image as ImageIcon,
  MessageSquare,
  MoreHorizontal,
  Paperclip,
  Pencil,
  Pin,
  Smile,
  Trash2,
} from "lucide-react";
import { Avatar } from "./Avatar";
import { Menu } from "./Menu";
import { formatBytes, formatTime } from "../lib/format";
import { fileUrl } from "../lib/api";
import { fetchFile, saveFile } from "../lib/desktop";
import { useSettings } from "../lib/settings";
import { QUICK_REACTIONS, renderBody } from "../lib/markdown";
import { useStore, type ReplyScope } from "../store/useStore";
import type { FileRef, Member, Message, Reaction } from "../lib/types";

interface Props {
  message: Message;
  grouped: boolean;
  own: boolean;
  onOpenThread: (message: Message) => void;
  onReact: (message: Message, emoji: string) => void;
  onEdit: (message: Message, body: string) => void;
  onDelete: (message: Message) => void;
  onPin: (message: Message) => void;
  /** Where an answer to this message is written. */
  replyScope?: ReplyScope;
  hideThread?: boolean;
  /** Put the avatar on the name line instead of in a column of its own. */
  flat?: boolean;
}

/** A quoted message is a line, never a paragraph. */
function snippet(body: string, limit = 60): string {
  const flat = body.replace(/\s+/g, " ").trim();
  return flat.length > limit ? `${flat.slice(0, limit)}…` : flat;
}

/** The people behind a reaction, in the order they pressed it. */
function reactorNames(ids: string[], members: Member[]): string[] {
  return ids
    .map((id) => members.find((member) => member.user.id === id)?.user.name)
    .filter((name): name is string => Boolean(name));
}

/** The gap between a message's words and the tools that act on them. */
const TOOL_GAP = 8;

/** One line of a message's words. */
interface Line {
  /** The middle of the line, vertically. */
  mid: number;
  /** The right edge of the line's ink. */
  right: number;
}

/**
 * The last line of ink in an element: where it sits and where its words
 * end. Measured from the last character that is not whitespace, so a
 * trailing space or a final line break cannot push the tools away from
 * the words they belong to.
 */
function lastInkLine(el: HTMLElement): Line | null {
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  const nodes: Text[] = [];
  while (walker.nextNode()) nodes.push(walker.currentNode as Text);
  for (let n = nodes.length - 1; n >= 0; n--) {
    const node = nodes[n];
    const text = node.nodeValue ?? "";
    for (let i = text.length - 1; i >= 0; i--) {
      if (!/\S/.test(text[i])) continue;
      const range = document.createRange();
      range.setStart(node, i);
      range.setEnd(node, i + 1);
      const rect = range.getBoundingClientRect();
      if (rect.width === 0 && rect.height === 0) continue;
      return {
        mid: (rect.top + rect.bottom) / 2,
        right: rect.right,
      };
    }
  }
  return null;
}

/**
 * The first line of a message's words: where it sits vertically. Only the
 * band is wanted here, so the bands of the laid-out text are enough.
 */
function firstLineBand(el: HTMLElement): number | null {
  const range = document.createRange();
  range.selectNodeContents(el);
  let top = Infinity;
  let mid = 0;
  for (const rect of Array.from(range.getClientRects())) {
    if (rect.height <= 0 || rect.width <= 0) continue;
    if (rect.top < top) {
      top = rect.top;
      mid = (rect.top + rect.bottom) / 2;
    }
  }
  return Number.isFinite(top) ? mid : null;
}

/**
 * The end of a message that carries no words: where its files stop. A
 * picture still has an edge the tools can stand against.
 */
function lastFileEdge(row: HTMLElement): Line | null {
  const files = row.querySelectorAll<HTMLElement>(".msg__file");
  const last = files[files.length - 1];
  if (!last) return null;
  const rect = last.getBoundingClientRect();
  if (rect.width === 0 && rect.height === 0) return null;
  return {
    mid: (rect.top + rect.bottom) / 2,
    right: rect.right,
  };
}

/** Where a message's tools sit, relative to the row that holds them. */
interface Spot {
  left: number;
  top: number;
}

/**
 * The tools belong to the message they act on, so they stand against it,
 * on the side that faces the middle of the conversation: just past the last
 * word for someone else's message, just before the bubble for your own. The
 * words are measured, because where they end depends on the width of the
 * pane and on the length of the message.
 *
 * Where the pane is too narrow to hold them beside the message, they float
 * above the row instead — still on the message's own side of the pane.
 */
function measureSpot(row: HTMLElement, tools: HTMLElement, own: boolean): Spot {
  const rowBox = row.getBoundingClientRect();
  const style = getComputedStyle(row);
  const contentLeft = rowBox.left + (parseFloat(style.paddingLeft) || 0);
  const contentRight = rowBox.right - (parseFloat(style.paddingRight) || 0);
  const width = tools.offsetWidth;
  const height = tools.offsetHeight;
  const body = row.querySelector<HTMLElement>(".msg__body");
  const bubble = row.querySelector<HTMLElement>(".msg__bubble");

  // Where the tools would sit if the pane had room for them there.
  let left: number;
  let band: number;
  if (own) {
    // Your own words travel in a bubble against the right of the pane, so
    // the tools stand on the paper to the bubble's left. While the message
    // is being edited the bubble still holds the textarea, so they wait
    // there too.
    const bubbleBox = bubble ? bubble.getBoundingClientRect() : null;
    const first = body ? firstLineBand(body) : null;
    left = bubbleBox ? bubbleBox.left - TOOL_GAP - width : contentRight - width;
    band = first != null ? first - height / 2 : bubbleBox?.top ?? rowBox.top;
  } else {
    // Just past the last word, so the tools never cover them. A message
    // with nothing but files ends at its last file instead.
    const last = body ? lastInkLine(body) : null;
    const edge = last ?? lastFileEdge(row);
    left = edge ? edge.right + TOOL_GAP : contentLeft;
    band = edge ? edge.mid - height / 2 : rowBox.top;
  }

  if (left < contentLeft || left + width > contentRight) {
    // No room beside the message: the tools float above the row, at the
    // edge their own message reaches.
    const edge = own ? contentRight - width : left;
    return {
      left: Math.round(
        Math.min(Math.max(edge, contentLeft), contentRight - width) - rowBox.left,
      ),
      top: -13,
    };
  }
  return { left: Math.round(left - rowBox.left), top: Math.round(band - rowBox.top) };
}

export function MessageRow({
  message,
  grouped,
  own,
  onOpenThread,
  onReact,
  onEdit,
  onDelete,
  onPin,
  replyScope = "channel",
  hideThread = false,
  flat = false,
}: Props) {
  const [menuAnchor, setMenuAnchor] = useState<HTMLElement | null>(null);
  const [emojiAnchor, setEmojiAnchor] = useState<HTMLElement | null>(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(message.body);
  const moreRef = useRef<HTMLButtonElement>(null);
  const rowRef = useRef<HTMLElement>(null);
  const toolsRef = useRef<HTMLDivElement>(null);
  const setReplyTo = useStore((s) => s.setReplyTo);
  const members = useStore((s) => s.members);
  const toast = useStore((s) => s.toast);
  const settings = useSettings();
  const [tip, setTip] = useState<{
    emoji: string;
    anchor: HTMLButtonElement;
    left: number;
    top: number;
    below: boolean;
  } | null>(null);

  const deleted = Boolean(message.deleted_at);

  /**
   * 파일을 눌렀을 때. 설정이 “폴더에 저장”이고 폴더가 있으면 그곳에
   * 내려받아 넣고, 그렇지 않으면 원래 위치에서 열린다.
   */
  const openFile = async (event: MouseEvent<HTMLAnchorElement>, file: FileRef) => {
    const folder = settings.downloadFolder;
    if (settings.fileOpen !== "save" || !folder) return;
    event.preventDefault();
    try {
      const bytes = await fetchFile(fileUrl(file.url));
      await saveFile(folder, file.name, bytes);
      toast(`${file.name} 저장했습니다`);
    } catch {
      toast("파일을 저장하지 못했습니다");
    }
  };

  // The quote names the message it answers; clicking it walks back to it.
  // In a thread the root is already right above, so quoting it is noise.
  const quote =
    replyScope === "thread" && message.reply_to_id === message.parent_id
      ? null
      : message.reply_to;
  const jumpToQuote = () => {
    if (!quote) return;
    const node = document.getElementById(quote.id);
    if (!node) return;
    // The scroller is walked by hand: the browser's own scrollIntoView can
    // settle on the window instead of the list the message lives in.
    const scroller = node.closest<HTMLElement>(".scroll");
    if (scroller) {
      const box = node.getBoundingClientRect();
      const view = scroller.getBoundingClientRect();
      const top =
        scroller.scrollTop +
        (box.top - view.top) -
        (scroller.clientHeight - box.height) / 2;
      scroller.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
    } else {
      node.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    node.classList.add("msg--pointed");
    window.setTimeout(() => node.classList.remove("msg--pointed"), 1400);
  };

  /**
   * The tools are placed against the message they act on, so they follow its
   * words rather than the row's far edge. The measurement waits for the
   * pointer: one row at a time, and only when the tools are about to show.
   */
  const placeTools = useCallback(() => {
    const row = rowRef.current;
    const tools = toolsRef.current;
    if (!row || !tools) return;
    const spot = measureSpot(row, tools, own);
    tools.style.left = `${spot.left}px`;
    tools.style.top = `${spot.top}px`;
    tools.style.right = "auto";
    // Only now do they belong where they are: the reveal waits for this,
    // so they never appear at the row's far edge first.
    tools.dataset.placed = "true";
  }, [own]);

  // A row under the pointer is watched: when its words move — the pane
  // narrowed, an edit made them longer — the tools move with them.
  useEffect(() => {
    const row = rowRef.current;
    if (!row) return;
    const observer = new ResizeObserver(() => {
      if (row.matches(":hover")) placeTools();
    });
    observer.observe(row);
    return () => observer.disconnect();
  }, [placeTools]);

  // Who pressed it: a reaction is a number until you ask who.
  const nameOf = (reaction: Reaction): string => {
    const names = reactorNames(reaction.user_ids, members);
    if (!names.length) return `${reaction.count}명이 반응했습니다`;
    if (names.length > 5) return `${names.slice(0, 5).join(", ")} 외 ${names.length - 5}명`;
    return names.join(", ");
  };

  const showTip = (
    event: MouseEvent<HTMLButtonElement> | FocusEvent<HTMLButtonElement>,
    reaction: Reaction,
  ) => {
    const rect = event.currentTarget.getBoundingClientRect();
    // The list scrolls: there may be no room above the chip.
    const below = rect.top < 120;
    setTip({
      emoji: reaction.emoji,
      anchor: event.currentTarget,
      left: rect.left + rect.width / 2,
      top: below ? rect.bottom + 8 : rect.top - 8,
      below,
    });
  };

  // The tip names who pressed the reaction as it stands now, not as it stood
  // when the pointer landed on the chip: pressing it again, or joining it,
  // shows up in the open tip at once.
  const tipReaction = tip
    ? message.reactions.find((reaction) => reaction.emoji === tip.emoji)
    : undefined;

  // Chips shift when a reaction is added or removed, so the tip is measured
  // again whenever the reaction set changes.
  useLayoutEffect(() => {
    const anchor = tip?.anchor;
    if (!anchor) return;
    const rect = anchor.getBoundingClientRect();
    const below = rect.top < 120;
    const left = rect.left + rect.width / 2;
    const top = below ? rect.bottom + 8 : rect.top - 8;
    setTip((prev) =>
      prev && (prev.left !== left || prev.top !== top || prev.below !== below)
        ? { ...prev, left, top, below }
        : prev,
    );
  }, [tip?.anchor, message.reactions]);

  return (
    <article
      ref={rowRef}
      onPointerEnter={placeTools}
      className={`msg${grouped ? " msg--grouped" : ""}${flat ? " msg--flat" : ""}${own ? " msg--mine" : ""}`}
      id={message.id}
    >
      {flat || own ? null : (
        <div className="msg__gutter">
          {grouped ? (
            <span className="msg__stamp" aria-hidden="true">
              {formatTime(message.created_at)}
            </span>
          ) : (
            <Avatar user={message.author} size="md" title={message.author.name} />
          )}
        </div>
      )}

      <div className="msg__stack">
        {!grouped && !own ? (
          <div className="msg__head">
            {flat ? (
              <Avatar user={message.author} size="md" title={message.author.name} />
            ) : null}
            <button type="button" className="msg__author">
              {message.author.name}
            </button>
            <time className="msg__time" dateTime={message.created_at}>
              {formatTime(message.created_at)}
            </time>
            {message.edited_at ? <span className="msg__edited">수정됨</span> : null}
          </div>
        ) : null}

        <div
          className={`msg__bubble${own && !deleted && !editing ? " msg__bubble--mine" : ""}`}
        >
          {deleted ? (
            <p className="msg__body msg__deleted">삭제된 메시지입니다.</p>
          ) : editing ? (
            <div className="u-mt-1">
              <textarea
                className="field__input u-h-auto u-minh-72 u-full u-py-2"
                value={draft}
                autoFocus
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    onEdit(message, draft);
                    setEditing(false);
                  }
                  if (event.key === "Escape") {
                    setDraft(message.body);
                    setEditing(false);
                  }
                }}
                aria-label="메시지 수정"
              />
              <div className="u-mt-2 u-row u-row--center u-gap-2">
                <button
                  type="button"
                  className="btn btn--primary btn--sm"
                  onClick={() => {
                    onEdit(message, draft);
                    setEditing(false);
                  }}
                >
                  저장
                </button>
                <button
                  type="button"
                  className="btn btn--sm"
                  onClick={() => {
                    setDraft(message.body);
                    setEditing(false);
                  }}
                >
                  취소
                </button>
              </div>
            </div>
          ) : (
            <>
              {quote ? (
                <button
                  type="button"
                  className="msg__quote"
                  onClick={jumpToQuote}
                  title="원문으로 이동"
                >
                  <CornerUpLeft size={12} aria-hidden="true" />
                  <span className="msg__quote-name">
                    {quote.deleted ? "삭제된 메시지" : quote.author_name}
                  </span>
                  {!quote.deleted && quote.body ? (
                    <span className="msg__quote-body">{snippet(quote.body)}</span>
                  ) : null}
                </button>
              ) : null}
              <div
                className="msg__body"
                dangerouslySetInnerHTML={{ __html: renderBody(message.body) }}
              />
            </>
          )}

          {own && !deleted && !editing ? (
            <div className="msg__when">
              <time dateTime={message.created_at}>{formatTime(message.created_at)}</time>
              {message.edited_at ? <span className="msg__edited">수정됨</span> : null}
            </div>
          ) : null}
        </div>

        {message.attachments.length ? (
          <div className="msg__files">
            {message.attachments.map((file) =>
              settings.imagePreview && file.mime.startsWith("image/") ? (
                <a
                  key={file.id}
                  className="msg__file"
                  href={fileUrl(file.url)}
                  target="_blank"
                  rel="noreferrer noopener"
                  onClick={(event) => void openFile(event, file)}
                >
                  <img src={fileUrl(file.url)} alt={file.name} />
                </a>
              ) : (
                <a
                  key={file.id}
                  className="msg__file u-row u-row--center u-gap-2 u-px-3 u-py-2 u-small"
                  href={fileUrl(file.url)}
                  target="_blank"
                  rel="noreferrer noopener"
                  onClick={(event) => void openFile(event, file)}
                >
                  {file.mime.startsWith("image/") ? (
                    <ImageIcon size={13} aria-hidden="true" />
                  ) : (
                    <Paperclip size={13} aria-hidden="true" />
                  )}
                  <span className="u-truncate">{file.name}</span>
                  <span className="u-tiny u-muted">{formatBytes(file.size)}</span>
                </a>
              ),
            )}
          </div>
        ) : null}

        {message.reactions.length ? (
          <div className="msg__reactions">
            {message.reactions.map((reaction) => (
              <button
                key={reaction.emoji}
                type="button"
                className={`reaction${reaction.me ? " reaction--mine" : ""}`}
                onClick={() => onReact(message, reaction.emoji)}
                onMouseEnter={(event) => showTip(event, reaction)}
                onMouseLeave={() => setTip(null)}
                onFocus={(event) => showTip(event, reaction)}
                onBlur={() => setTip(null)}
                aria-pressed={reaction.me}
                aria-describedby={tipReaction && tip?.emoji === reaction.emoji ? "reactiontip" : undefined}
                aria-label={`${reaction.emoji} ${reaction.count}명 반응: ${nameOf(reaction)}`}
              >
                <span aria-hidden="true">{reaction.emoji}</span>
                <span className="reaction__count">{reaction.count}</span>
              </button>
            ))}
          </div>
        ) : null}

        {message.reply_count > 0 && !hideThread ? (
          <button type="button" className="msg__thread" onClick={() => onOpenThread(message)}>
            <MessageSquare size={13} aria-hidden="true" />
            답글 {message.reply_count}개
          </button>
        ) : null}
      </div>

      <div
        ref={toolsRef}
        className="msg__tools"
        role="group"
        aria-label="메시지 동작"
        onFocus={placeTools}
      >
        <button
          type="button"
          className="iconbtn"
          aria-label="반응 추가"
          aria-expanded={Boolean(emojiAnchor)}
          onClick={(event) => setEmojiAnchor(event.currentTarget)}
        >
          <Smile size={15} aria-hidden="true" />
        </button>
        <button
          type="button"
          className="iconbtn"
          aria-label="스레드로 답글"
          onClick={() => onOpenThread(message)}
        >
          <MessageSquare size={15} aria-hidden="true" />
        </button>
        <button
          type="button"
          className="iconbtn"
          aria-label="이 메시지에 답장"
          onClick={() => setReplyTo(message, replyScope)}
        >
          <CornerUpLeft size={15} aria-hidden="true" />
        </button>
        {own && !deleted ? (
          <button
            type="button"
            className="iconbtn msg__tools--danger"
            aria-label="메시지 삭제"
            onClick={() => onDelete(message)}
          >
            <Trash2 size={15} aria-hidden="true" />
          </button>
        ) : null}
        <button
          ref={moreRef}
          type="button"
          className="iconbtn"
          aria-label="더 보기"
          aria-expanded={Boolean(menuAnchor)}
          onClick={(event) => setMenuAnchor(event.currentTarget)}
        >
          <MoreHorizontal size={15} aria-hidden="true" />
        </button>
      </div>

      {emojiAnchor ? (
        <Menu
          anchor={emojiAnchor}
          onClose={() => setEmojiAnchor(null)}
          className="emoji"
          width={280}
        >
          <div className="emoji__grid" role="menu" aria-label="반응 선택">
            {QUICK_REACTIONS.map((emoji) => (
              <button
                key={emoji}
                type="button"
                className="emoji__item"
                onClick={() => {
                  onReact(message, emoji);
                  setEmojiAnchor(null);
                }}
              >
                {emoji}
              </button>
            ))}
          </div>
        </Menu>
      ) : null}

      {menuAnchor ? (
        <Menu anchor={menuAnchor} onClose={() => setMenuAnchor(null)} align="right" width={200}>
          {!deleted ? (
            <button
              type="button"
              className="menu__item"
              onClick={() => {
                setMenuAnchor(null);
                setDraft(message.body);
                setEditing(true);
              }}
            >
              <Pencil size={14} aria-hidden="true" />
              텍스트 수정
            </button>
          ) : null}
          <button
            type="button"
            className="menu__item"
            onClick={() => {
              setMenuAnchor(null);
              onPin(message);
            }}
          >
            <Pin size={14} aria-hidden="true" />
            {message.pinned ? "고정 해제" : "고정하기"}
          </button>
          <button
            type="button"
            className="menu__item"
            onClick={() => {
              setMenuAnchor(null);
              void navigator.clipboard?.writeText(message.body);
            }}
          >
            <Copy size={14} aria-hidden="true" />
            본문 복사
          </button>
          {own ? (
            <>
              <div className="menu__sep" />
              <button
                type="button"
                className="menu__item menu__item--danger"
                onClick={() => {
                  setMenuAnchor(null);
                  onDelete(message);
                }}
              >
                <Trash2 size={14} aria-hidden="true" />
                삭제
              </button>
            </>
          ) : null}
        </Menu>
      ) : null}

      {tip && tipReaction
        ? createPortal(
            <div
              id="reactiontip"
              className={`reactiontip${tip.below ? " reactiontip--below" : ""}`}
              role="tooltip"
              style={{ left: tip.left, top: tip.top }}
            >
              {nameOf(tipReaction)}
            </div>,
            document.body,
          )
        : null}
    </article>
  );
}
