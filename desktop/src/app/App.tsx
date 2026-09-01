/**
 * The application shell and the realtime event bridge.
 *
 * All shell -> UI events are wired up in one place here, so there is a single
 * answer to "what happens when the server says X".
 */

import { useEffect, useState } from "react";

import { AppDock } from "@/components/AppDock";
import { AppPanel } from "@/components/AppPanel";
import { Banner } from "@/components/Banner";
import { ChannelHeader } from "@/components/ChannelHeader";
import { CommandPalette } from "@/components/CommandPalette";
import { Composer } from "@/components/Composer";
import { MessageList } from "@/components/MessageList";
import { Sidebar } from "@/components/Sidebar";
import { SignIn } from "@/components/SignIn";
import { ThreadPane } from "@/components/ThreadPane";
import { events, type UnlistenFn } from "@/lib/ipc";
import { useApp } from "@/store/app";

const FALLBACK_SERVER = "http://localhost:8000";

export function App() {
  const screen = useApp((state) => state.screen);
  const [defaultServer, setDefaultServer] = useState(FALLBACK_SERVER);

  useRealtimeBridge(setDefaultServer);
  useKeyboardShortcuts();

  if (screen === "loading") {
    return (
      <div className="boot">
        <div className="boot-spinner" aria-label="불러오는 중" />
      </div>
    );
  }

  if (screen === "signin") {
    return (
      <>
        <Banner />
        <SignIn defaultServerUrl={defaultServer} />
      </>
    );
  }

  return (
    <div className="shell">
      <AppDock />
      <Sidebar />
      <main className="main">
        <ChannelHeader />
        <Banner />
        <div className="main-body">
          <div className="main-transcript">
            <MessageList />
            <Composer />
          </div>
          <ThreadPane />
          <AppPanel />
        </div>
      </main>
      <CommandPalette />
    </div>
  );
}

/** Subscribe to every shell event and route it into the store. */
function useRealtimeBridge(setDefaultServer: (url: string) => void) {
  useEffect(() => {
    const store = useApp.getState;
    const unlisteners: Array<Promise<UnlistenFn>> = [];
    let bootstrapped = false;

    unlisteners.push(
      events.onReady((payload) => {
        setDefaultServer(payload.default_server_url);
        // The shell tells us its configured server; connect to it once.
        if (!bootstrapped) {
          bootstrapped = true;
          void store().bootstrap(payload.default_server_url);
        }
      }),
    );

    unlisteners.push(events.onConnection((status) => store().onConnection(status)));

    unlisteners.push(
      events.onSync((effect) => {
        switch (effect.kind) {
          case "channel_changed":
            void store().applyChannelChanged(effect.channel_id);
            break;
          case "thread_changed":
            void store().applyThreadChanged(effect.parent_id);
            break;
          case "sidebar_changed":
            void store().refreshSidebar();
            break;
          case "typing":
            store().applyTyping(effect.channel_id, effect.user_id);
            break;
          case "presence":
            store().applyPresence(effect.user_id, effect.presence);
            break;
          case "notify":
            // The OS notification is shown by the shell; the sidebar counters
            // are what the UI needs to update.
            void store().refreshSidebar();
            break;
          case "ignored":
            break;
        }
      }),
    );

    unlisteners.push(events.onBadge((payload) => store().setBadge(payload.count)));

    unlisteners.push(
      events.onAuthLost((payload) => store().handleAuthLost(payload.message)),
    );

    unlisteners.push(
      events.onPresenceRequest((payload) => {
        void store().setPresence(payload.presence as "active" | "away" | "dnd");
      }),
    );

    unlisteners.push(
      events.onDeepLink((payload) => {
        for (const raw of payload.urls) {
          handleDeepLink(raw);
        }
      }),
    );

    // The ready event may already have fired before this effect ran (a fast
    // shell beats React's first commit), so connect to the fallback if nothing
    // arrived shortly.
    const fallbackTimer = setTimeout(() => {
      if (!bootstrapped && useApp.getState().screen === "loading") {
        bootstrapped = true;
        void store().bootstrap(FALLBACK_SERVER);
      }
    }, 1_200);

    return () => {
      clearTimeout(fallbackTimer);
      for (const pending of unlisteners) {
        void pending.then((unlisten) => unlisten()).catch(() => {
          /* the window is going away anyway */
        });
      }
    };
  }, [setDefaultServer]);
}

/** `llack://` links: invitations and deep links into a channel or message. */
function handleDeepLink(raw: string) {
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    return;
  }
  const store = useApp.getState();

  if (url.host === "invite" || url.pathname.startsWith("//invite")) {
    const token = url.searchParams.get("token");
    if (token) {
      store.showBanner(
        "info",
        "초대 링크를 받았습니다. 로그인 후 자동으로 참여합니다.",
      );
    }
    return;
  }

  const channelId = url.searchParams.get("channel");
  if (channelId) void store.openChannel(channelId);
}

/** Global shortcuts handled in the webview. */
function useKeyboardShortcuts() {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const store = useApp.getState();
      const modifier = event.metaKey || event.ctrlKey;

      if (modifier && event.key.toLowerCase() === "k") {
        event.preventDefault();
        store.setPalette(!store.paletteOpen);
        return;
      }
      if (event.key === "Escape") {
        if (store.paletteOpen) {
          store.setPalette(false);
        } else if (store.openThreadId) {
          void store.openThread(null);
        } else if (store.openPanelInstallationId) {
          store.openAppPanel(null);
        }
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);
}
