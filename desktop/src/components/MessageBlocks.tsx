/**
 * Rich blocks beside a message's Markdown: link unfurls, app sections, and
 * interactive buttons/selects.
 *
 * Text inside blocks is rendered as text — never HTML — so an app cannot
 * inject markup. Actions post back through the server, which signs and
 * forwards them to the app; the app may replace the message or answer only
 * to the person who clicked (an ephemeral line shown under the message).
 */

import { useState } from "react";

import { api } from "@/lib/ipc";
import { isPreviewableImage } from "@/lib/preview";
import type { FileRef, Message, MessageBlock } from "@/lib/types";
import { useApp } from "@/store/app";

import { IconGlobe } from "./Icon";

export function MessageBlocks({ message }: { message: Message }) {
  const reportError = useApp((state) => state.reportError);
  const [busy, setBusy] = useState<string | null>(null);
  const [ephemeral, setEphemeral] = useState<string | null>(null);

  const blocks = (message.blocks ?? []).filter(
    (block): block is MessageBlock => !!block && typeof block === "object" && "type" in block,
  );
  if (blocks.length === 0) return null;

  const act = async (actionId: string, value?: string | null) => {
    setBusy(actionId);
    try {
      const result = await api.messageAction(message.id, actionId, value ?? null);
      if (result.ephemeral?.text) setEphemeral(result.ephemeral.text);
    } catch (error) {
      reportError(error, "앱이 응답하지 않았습니다.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="message-blocks">
      {blocks.map((block, index) => {
        switch (block.type) {
          case "unfurl":
            return <Unfurl key={`${block.url}-${index}`} block={block} />;
          case "section":
            return (
              <p key={index} className="block-section">
                {block.text}
              </p>
            );
          case "context":
            return (
              <p key={index} className="block-context">
                {block.text}
              </p>
            );
          case "actions":
            return (
              <div key={index} className="block-actions" role="group" aria-label="앱 동작">
                {block.elements.map((element, elementIndex) =>
                  element.type === "button" ? (
                    <button
                      key={`${element.action_id}-${elementIndex}`}
                      type="button"
                      className={`block-button ${element.style === "primary" ? "is-primary" : ""} ${
                        element.style === "danger" ? "is-danger" : ""
                      }`}
                      onClick={() => void act(element.action_id, element.value ?? null)}
                      disabled={busy !== null}
                    >
                      {element.text}
                    </button>
                  ) : (
                    <select
                      key={`${element.action_id}-${elementIndex}`}
                      className="block-select"
                      defaultValue=""
                      onChange={(event) => {
                        if (event.target.value) void act(element.action_id, event.target.value);
                      }}
                      disabled={busy !== null}
                      aria-label={element.placeholder ?? "선택"}
                    >
                      <option value="" disabled>
                        {element.placeholder ?? "선택…"}
                      </option>
                      {element.options.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.text}
                        </option>
                      ))}
                    </select>
                  ),
                )}
              </div>
            );
          default:
            return null;
        }
      })}
      {ephemeral ? <p className="block-ephemeral">나에게만 보임 · {ephemeral}</p> : null}
    </div>
  );
}

function Unfurl({ block }: { block: Extract<MessageBlock, { type: "unfurl" }> }) {
  let host = "";
  try {
    host = new URL(block.url).host;
  } catch {
    // Malformed URL: the card still shows what the server extracted.
  }
  if (!block.title && !block.description) return null;
  return (
    <a
      className="unfurl"
      href={block.url}
      target="_blank"
      rel="noreferrer noopener"
      title={block.url}
    >
      <div className="unfurl-text">
        <span className="unfurl-site">
          <IconGlobe size={11} /> {block.site_name || host}
        </span>
        {block.title ? <strong>{block.title}</strong> : null}
        {block.description ? <p>{block.description}</p> : null}
      </div>
      {block.image_url ? (
        <img
          className="unfurl-image"
          src={block.image_url}
          alt=""
          loading="lazy"
          referrerPolicy="no-referrer"
        />
      ) : null}
    </a>
  );
}

/** Whether a file can play inline. Mirrors the image cap: big videos stream. */
export function isInlineVideo(file: FileRef): boolean {
  return file.mime_type.startsWith("video/") && !isPreviewableImage(file);
}
