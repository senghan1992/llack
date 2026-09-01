import { useEffect, useState } from "react";

import { channelPrefix } from "@/lib/format";
import { TYPING_TTL_MS, typingNames, useApp } from "@/store/app";

export function ChannelHeader() {
  const channel = useApp((state) =>
    state.channels.find((candidate) => candidate.id === state.activeChannelId),
  );
  // Selected as stable references; the names are derived below. A selector that
  // returned a fresh array here would re-render forever.
  const typingEntries = useApp((state) =>
    state.activeChannelId ? state.typing.get(state.activeChannelId) : undefined,
  );
  const people = useApp((state) => state.people);
  const toggleMute = useApp((state) => state.toggleMute);
  const setPalette = useApp((state) => state.setPalette);
  const connection = useApp((state) => state.connection);

  // Entries expire by wall clock, so nudge a render when the newest one ages
  // out — otherwise "입력 중…" lingers until the next store change.
  const [, expire] = useState(0);
  useEffect(() => {
    if (!typingEntries || typingEntries.length === 0) return undefined;
    const timer = window.setTimeout(() => expire((n) => n + 1), TYPING_TTL_MS);
    return () => window.clearTimeout(timer);
  }, [typingEntries]);

  const typing = typingNames(typingEntries, people);

  if (!channel) {
    return (
      <header className="channel-header">
        <button type="button" className="palette-trigger" onClick={() => setPalette(true)}>
          검색하거나 이동 (⌘K)
        </button>
      </header>
    );
  }

  const isDm = channel.kind === "dm" || channel.kind === "group_dm";
  const title = channel.name ?? channel.peers.map((p) => p.display_name).join(", ");
  const muted = channel.membership?.is_muted ?? false;

  return (
    <header className="channel-header">
      <div className="channel-title">
        <h1>
          <span className="channel-title-prefix">{channelPrefix(channel.kind)}</span>
          {title}
        </h1>
        {!isDm ? (
          <span className="channel-meta">{channel.member_count}명</span>
        ) : null}
        {channel.topic ? <span className="channel-topic">{channel.topic}</span> : null}
      </div>

      <div className="channel-header-right">
        {connection && connection.status !== "connected" ? (
          <span className="connection-chip" title={describeConnection(connection)}>
            {connection.status === "resyncing" ? "동기화 중…" : "연결 끊김"}
          </span>
        ) : null}
        {typing.length > 0 ? (
          <span className="typing-indicator">
            {typing.slice(0, 2).join(", ")}
            {typing.length > 2 ? ` 외 ${typing.length - 2}명` : ""} 입력 중…
          </span>
        ) : null}
        <button
          type="button"
          className="header-button"
          onClick={() => void toggleMute(channel.id)}
          title={muted ? "알림 켜기" : "알림 끄기"}
        >
          {muted ? "🔕" : "🔔"}
        </button>
        <button
          type="button"
          className="palette-trigger"
          onClick={() => setPalette(true)}
        >
          검색 (⌘K)
        </button>
      </div>
    </header>
  );
}

function describeConnection(connection: NonNullable<ReturnType<typeof useApp.getState>["connection"]>): string {
  if (connection.status === "disconnected") {
    const retry = connection.will_retry_in_ms;
    return retry
      ? `${connection.reason} · ${Math.round(retry / 1000)}초 후 재시도`
      : connection.reason;
  }
  if (connection.status === "resyncing") {
    return "누락된 이벤트를 복구하고 있습니다.";
  }
  return "연결됨";
}
