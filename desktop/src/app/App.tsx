/**
 * The application shell and the realtime event bridge.
 *
 * All shell -> UI events are wired up in one place here, so there is a single
 * answer to "what happens when the server says X".
 */

import { useEffect, useState } from "react";

import { AppDock } from "@/components/AppDock";
import { AgentPanel } from "@/components/AgentPanel";
import { AppPanel } from "@/components/AppPanel";
import { Banner } from "@/components/Banner";
import { Notices } from "@/components/Notices";
import { ChannelHeader } from "@/components/ChannelHeader";
import { CommandPalette } from "@/components/CommandPalette";
import { Composer } from "@/components/Composer";
import { MessageList } from "@/components/MessageList";
import { NoWorkspace } from "@/components/NoWorkspace";
import { Settings } from "@/components/Settings";
import { Sidebar } from "@/components/Sidebar";
import { SignIn } from "@/components/SignIn";
import { ThreadPane } from "@/components/ThreadPane";
import { WebAppView } from "@/components/WebAppView";
import { captureInviteFromLocation } from "@/lib/invite";
import { events, type UnlistenFn } from "@/lib/ipc";
import { useAgent } from "@/store/agent";
import { useApp } from "@/store/app";

const FALLBACK_SERVER = "http://localhost:8000";

// Before anything renders or the bridge rewrites history: an `?invite=` in
// the address is parked for redemption after sign-in.
captureInviteFromLocation();

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

  return <WorkspaceShell />;
}

/** The signed-in surface: the workspace, or the "belongs to none yet" card. */
function WorkspaceShell() {
  const hasWorkspace = useApp((state) => state.workspaces.length > 0);
  const workspacesLoaded = useApp((state) => state.workspacesLoaded);

  if (workspacesLoaded && !hasWorkspace) {
    return (
      <>
        <Banner />
        <NoWorkspace />
        <Notices />
      </>
    );
  }

  return (
    <div className="shell">
      <AppDock />
      <Sidebar />
      <main className="main">
        {/*
          Connection state and errors sit above the row of sheets, on the
          ground: they are about the whole workspace, not about the channel you
          happen to be reading.
        */}
        <Banner />
        <div className="main-body">
          {/*
            The channel header belongs to the transcript, not to the row. It
            used to span every open sheet, which put a channel's name and
            member count over a thread and an agent panel that are not the
            channel — and it stopped each sheet from being its own card.
          */}
          <MainPane />
          <ThreadPane />
          <AppPanel />
          <AgentPanel />
        </div>
      </main>
      <CommandPalette />
      <Settings />
      <Notices />
    </div>
  );
}

/**
 * The main pane: the transcript, unless a link app has borrowed the seat.
 *
 * One seat, two occupants, never both — an embedded dashboard next to a
 * half-visible transcript would be two half-products. Opening a channel gives
 * the seat back (the store clears the web app there).
 */
function MainPane() {
  const webAppId = useApp((state) => state.openWebAppInstallationId);
  const installation = useApp((state) =>
    state.installations.find((entry) => entry.id === state.openWebAppInstallationId),
  );

  if (webAppId && installation) {
    return (
      <div className="main-transcript">
        <WebAppView installation={installation} />
      </div>
    );
  }
  return (
    <div className="main-transcript">
      <ChannelHeader />
      <MessageList />
      <Composer />
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

    // `message.created` carries the mention targets that the shared
    // notification payload cannot; the store uses it to tell a mention from
    // ordinary channel traffic.
    unlisteners.push(events.onFrame((frame) => store().noteIncomingFrame(frame)));

    unlisteners.push(
      events.onSync((effect) => {
        switch (effect.kind) {
          case "channel_changed":
            void store().applyChannelChanged(effect.channel_id);
            break;
          case "thread_changed":
            void store().applyThreadChanged(effect.parent_id);
            // A thread reply also changes the channel: the parent row's
            // "답글 N개" summary, and — with "채널에도 보내기" — the
            // transcript itself. Both runtimes map a threaded message to
            // thread_changed only, so the channel half is fanned out here,
            // where one line covers desktop and web alike.
            void store().applyChannelChanged(effect.channel_id);
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
            // The shell also raises an OS notification, but only while the
            // window is unfocused. This is the in-app half, and it is what a
            // focused user reading another channel actually sees.
            store().pushNotice(effect);
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
        if (store.settingsOpen) {
          store.setSettings(false);
        } else if (store.paletteOpen) {
          store.setPalette(false);
        } else if (store.openThreadId) {
          void store.openThread(null);
        } else if (store.openPanelInstallationId) {
          store.openAppPanel(null);
        } else if (useAgent.getState().open) {
          // Last on the ladder, and only when nothing is pending: the approval
          // card handles its own Escape as a denial and stops propagation, so
          // Escape can never close the panel out from under a decision.
          useAgent.getState().setOpen(false);
        }
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);
}
