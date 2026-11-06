/**
 * 화면 모드.
 *
 * `light` · `dark` 는 그대로이고, `system` 은 OS 설정을 따라간다 —
 * OS 가 밤으로 넘어가면 앱도 어두워진다. 창이 떠 있을 때 OS 설정을 바꾸면
 * 바로 따라간다.
 */

import { getSettings, subscribeSettings, type ThemeMode } from "./settings";

const DARK_QUERY = "(prefers-color-scheme: dark)";

/** 모드가 지금 어떤 화면인지 — `system` 은 OS 의 답을 빌려 온다. */
export function resolvedTheme(mode: ThemeMode): "light" | "dark" {
  if (mode !== "system") return mode;
  try {
    return window.matchMedia(DARK_QUERY).matches ? "dark" : "light";
  } catch {
    return "light";
  }
}

/** 화면에 지금 적용된 모드. */
export function currentTheme(): "light" | "dark" {
  return resolvedTheme(getSettings().theme);
}

/** 마지막으로 칠한 모드. 같으면 다시 칠하지 않는다. */
let applied: "light" | "dark" | null = null;

/** 문서와 OS 창에 모드를 적용한다. */
export function applyTheme(): void {
  const mode = currentTheme();
  applied = mode;
  document.documentElement.dataset.theme = mode;
  void syncWindowTheme(mode);
}

/** 셸의 창(타이틀 바)도 같은 모드로 맞춘다. 웹에서 돌 때는 할 일 없다. */
async function syncWindowTheme(mode: "light" | "dark"): Promise<void> {
  try {
    const { invoke, isTauri } = await import("@tauri-apps/api/core");
    if (!(await isTauri())) return;
    await invoke("set_window_theme", { mode });
  } catch {
    /* 셸이 없거나 오래된 셸이면 화면만 맞춘다. */
  }
}

let listening = false;

/** 화면 모드를 따라가게 한다. 앱이 뜰 때 한 번 부른다. */
export function watchTheme(): void {
  if (listening) return;
  listening = true;

  const media = window.matchMedia(DARK_QUERY);
  const onChange = () => {
    if (getSettings().theme === "system") applyTheme();
  };
  if (media.addEventListener) media.addEventListener("change", onChange);
  else media.addListener?.(onChange);

  subscribeSettings(() => {
    const mode = currentTheme();
    if (mode !== applied) applyTheme();
  });

  applyTheme();
}
