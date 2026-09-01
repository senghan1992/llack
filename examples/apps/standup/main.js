/**
 * 데일리 스탠드업 — Llack 미니앱 참조 구현.
 *
 * Shows the whole shape of a panel app in one file:
 *   1. handshake with the host to get a scoped session,
 *   2. read the granted config and channel list,
 *   3. persist a draft in the app's own per-user storage,
 *   4. post to a channel as the app's bot user.
 *
 * Note what is *not* here: no API key, no OAuth dance, no database. The host
 * supplies a short-lived scoped token, and `llack.storage` is the app's
 * persistence.
 */

// Vendored by `make setup-sdk` / `make example-app`: the app is served with
// its own directory as the web root, so a path outside that root (the
// monorepo's packages/) is not reachable over HTTP.
import { createClient, LlackError } from "./vendor/llack-app-sdk/index.js";

const elements = {
  who: document.getElementById("who"),
  yesterday: document.getElementById("yesterday"),
  today: document.getElementById("today"),
  blockers: document.getElementById("blockers"),
  channel: document.getElementById("channel"),
  submit: document.getElementById("submit"),
  status: document.getElementById("status"),
  saved: document.getElementById("saved"),
};

const STORAGE_KEY = "draft";

function setStatus(message, kind = "") {
  elements.status.textContent = message;
  elements.status.className = `status ${kind}`;
}

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

async function main() {
  let llack;
  try {
    llack = await createClient();
  } catch (error) {
    setStatus(
      error instanceof LlackError
        ? `Llack에 연결할 수 없습니다: ${error.message}`
        : "Llack에 연결할 수 없습니다.",
      "error",
    );
    return;
  }

  const { user, channel_id: currentChannelId } = llack.context;
  elements.who.textContent = `${user.display_name} 님의 ${todayIso()} 스탠드업`;
  llack.ui.setTitle(`스탠드업 · ${todayIso()}`);

  // Channels the app may post to.
  try {
    const channels = await llack.channels.list();
    // A channel named in the install config wins; otherwise default to the
    // channel the user is currently looking at.
    const preferred =
      typeof llack.config.channel_slug === "string"
        ? channels.find((channel) => channel.slug === llack.config.channel_slug)
        : undefined;

    elements.channel.innerHTML = "";
    for (const channel of channels) {
      const option = document.createElement("option");
      option.value = channel.id;
      option.textContent = `#${channel.name ?? channel.slug ?? channel.id}`;
      elements.channel.append(option);
    }
    const initial = preferred?.id ?? currentChannelId ?? channels[0]?.id;
    if (initial) elements.channel.value = initial;
  } catch (error) {
    setStatus(`채널 목록을 불러오지 못했습니다: ${error.message}`, "error");
  }

  // Restore this user's own draft. Per-user scope, so drafts are private.
  try {
    const draft = await llack.storage.get(STORAGE_KEY, { user: user.id });
    if (draft && draft.date === todayIso()) {
      elements.yesterday.value = draft.yesterday ?? "";
      elements.today.value = draft.today ?? "";
      elements.blockers.value = draft.blockers ?? "";
      setStatus("저장된 임시 내용을 불러왔습니다.");
    }
    const history = await llack.storage.list("posted:", { user: user.id });
    if (history.length > 0) {
      const latest = history[history.length - 1];
      elements.saved.textContent = `마지막 제출: ${latest.key.replace("posted:", "")}`;
    }
  } catch (error) {
    // Storage is a convenience; the app still works without it.
    console.warn("draft restore failed", error);
  }

  // Autosave, debounced — losing a half-written standup is annoying.
  let saveTimer;
  const scheduleSave = () => {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
      void llack.storage
        .set(
          STORAGE_KEY,
          {
            date: todayIso(),
            yesterday: elements.yesterday.value,
            today: elements.today.value,
            blockers: elements.blockers.value,
          },
          { user: user.id },
        )
        .catch((error) => console.warn("draft save failed", error));
    }, 600);
  };
  for (const field of [elements.yesterday, elements.today, elements.blockers]) {
    field.addEventListener("input", scheduleSave);
  }

  elements.submit.disabled = false;
  elements.submit.addEventListener("click", async () => {
    const channelId = elements.channel.value;
    if (!channelId) {
      setStatus("올릴 채널을 선택해주세요.", "error");
      return;
    }
    if (!elements.today.value.trim()) {
      setStatus("오늘 할 일은 비워둘 수 없습니다.", "error");
      return;
    }

    elements.submit.disabled = true;
    setStatus("올리는 중…");

    const body = [
      `*${user.display_name}* 의 스탠드업 — ${todayIso()}`,
      "",
      "*어제 한 일*",
      elements.yesterday.value.trim() || "- (없음)",
      "",
      "*오늘 할 일*",
      elements.today.value.trim(),
      ...(elements.blockers.value.trim()
        ? ["", "*막힌 것*", elements.blockers.value.trim()]
        : []),
    ].join("\n");

    try {
      await llack.messages.post({
        channelId,
        body,
        // Idempotency key: a retry after a flaky network cannot double-post.
        clientMsgId: `standup-${user.id}-${todayIso()}`,
      });
      setStatus("채널에 올렸습니다.", "ok");
      await llack.storage.delete(STORAGE_KEY, { user: user.id });
      await llack.storage.set(`posted:${todayIso()}`, { channelId }, { user: user.id });
      elements.saved.textContent = `마지막 제출: ${todayIso()}`;
    } catch (error) {
      if (error instanceof LlackError && error.isMissingScope) {
        setStatus(
          "이 앱에 메시지 전송 권한이 없습니다. 관리자에게 권한을 요청해주세요.",
          "error",
        );
      } else {
        setStatus(`올리지 못했습니다: ${error.message}`, "error");
      }
    } finally {
      elements.submit.disabled = false;
    }
  });
}

void main();
