/**
 * 이 기기의 설정.
 *
 * 계정 것과 기기 것을 나눈다. 이름·직함·아바타·역할은 서버에 있고(계정),
 * 알림·화면·파일은 이 창을 쓰는 사람마다 다르고 이 기기에 남는 것(기기)이다.
 * 여기 저장되는 값은 한 줄의 JSON 이고, 창을 다시 열 때 그대로 읽는다.
 */

import { useSyncExternalStore } from "react";

/** 화면 모드 — `system` 은 OS 설정을 따라간다. */
export type ThemeMode = "light" | "dark" | "system";

/** 알림 본문에 메시지 내용을 보여줄까. */
export type NotificationPreview = "preview" | "subject";

/** 시간 표기. */
export type ClockFormat = "24h" | "12h";

/** 파일을 눌렀을 때. */
export type FileOpenMode = "open" | "save";

export interface Settings {
  /** OS 알림을 띄울까. */
  notifications: boolean;
  /** 알림 본문에 메시지 내용을 보여줄까. */
  notificationPreview: NotificationPreview;
  /** 화면 모드. */
  theme: ThemeMode;
  /** 시간 표기. */
  clock: ClockFormat;
  /** 파일을 눌렀을 때 — 원래 위치에서 열까, 폴더에 저장할까. */
  fileOpen: FileOpenMode;
  /** 다운로드 폴더. 데스크톱 셸에서만 뜻이 있다. */
  downloadFolder: string | null;
  /** 이미지를 메시지 안에 그대로 펼쳐 보여줄까. */
  imagePreview: boolean;
  /** 일정과 프로젝트를 대화 옆에 붙여 놓을까 — 화면을 나누는 방식. */
  splitView: boolean;
  /** 좌측 레일을 아이콘만 남은 띠로 접을까. */
  railCollapsed: boolean;
}

const KEY = "llack.settings";
/** 예전 버전은 테마만 따로 저장했다. 처음 읽을 때 옮겨 쓴다. */
const LEGACY_THEME_KEY = "llack.theme";

const DEFAULTS: Settings = {
  notifications: true,
  notificationPreview: "preview",
  theme: "light",
  clock: "24h",
  fileOpen: "open",
  downloadFolder: null,
  imagePreview: true,
  splitView: true,
  railCollapsed: false,
};

function oneOf<T extends string>(value: unknown, allowed: readonly T[], fallback: T): T {
  return allowed.includes(value as T) ? (value as T) : fallback;
}

/** 저장된 값을 읽는다. 잘못 저장되어 있으면 기본값으로 되돌린다. */
function read(): Settings {
  let stored: Partial<Settings> = {};
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) stored = JSON.parse(raw) as Partial<Settings>;
  } catch {
    /* 저장소를 못 읽어도 앱은 떠야 한다 — 기본값으로 간다. */
  }

  if (!stored.theme) {
    const legacy = localStorage.getItem(LEGACY_THEME_KEY);
    if (legacy === "light" || legacy === "dark") stored.theme = legacy;
  }

  return {
    notifications: typeof stored.notifications === "boolean" ? stored.notifications : DEFAULTS.notifications,
    notificationPreview: oneOf(
      stored.notificationPreview,
      ["preview", "subject"] as const,
      DEFAULTS.notificationPreview,
    ),
    theme: oneOf(stored.theme, ["light", "dark", "system"] as const, DEFAULTS.theme),
    clock: oneOf(stored.clock, ["24h", "12h"] as const, DEFAULTS.clock),
    fileOpen: oneOf(stored.fileOpen, ["open", "save"] as const, DEFAULTS.fileOpen),
    downloadFolder: typeof stored.downloadFolder === "string" ? stored.downloadFolder : null,
    imagePreview: typeof stored.imagePreview === "boolean" ? stored.imagePreview : DEFAULTS.imagePreview,
    splitView: typeof stored.splitView === "boolean" ? stored.splitView : DEFAULTS.splitView,
    railCollapsed:
      typeof stored.railCollapsed === "boolean" ? stored.railCollapsed : DEFAULTS.railCollapsed,
  };
}

let current: Settings = read();
const listeners = new Set<() => void>();

/** 지금의 설정. */
export function getSettings(): Settings {
  return current;
}

/** 설정을 고친다. 고른 값만 바뀌고, 고쳐진 사실은 알려 준다. */
export function setSettings(patch: Partial<Settings>): void {
  const next = { ...current, ...patch };
  const same = (Object.keys(next) as (keyof Settings)[]).every((key) => next[key] === current[key]);
  if (same) return;
  current = next;
  try {
    localStorage.setItem(KEY, JSON.stringify(current));
  } catch {
    /* 저장하지 못해도 화면은 그대로 동작한다. */
  }
  for (const listener of listeners) listener();
}

/** 설정이 바뀌면 알려 준다. */
export function subscribeSettings(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** 지금의 설정을 쓰는 컴포넌트. */
export function useSettings(): Settings {
  return useSyncExternalStore(subscribeSettings, getSettings, getSettings);
}

/** 설정을 고치는 컴포넌트. */
export function useSetSettings(): (patch: Partial<Settings>) => void {
  return setSettings;
}
