/**
 * The models the connected account can actually use.
 *
 * Fetched from the provider's own `/v1/models` through the byte proxy — the
 * same path every agent request takes, so the key never enters the webview and
 * the origin allowlist applies unchanged. This is what makes the settings
 * screen offer *the account's* models rather than a list this build guessed at:
 * a subscription that gains a model gains it here without an app update.
 *
 * Desktop only. A browser tab has no keychain and no proxy, and the scripted
 * fake it runs on has exactly one pretend model.
 */

import { createIpcFetch } from "./ipcFetch";

export interface ProviderModel {
  id: string;
  /** The provider's human name for it, e.g. "Claude Opus 5". */
  displayName: string;
}

/**
 * The fallback shown before the account has been asked.
 *
 * Used for the connect form's initial dropdown (the list endpoint needs a key,
 * and at that moment there is none) and kept deliberately short: after
 * connecting, the real list from the account replaces it.
 */
export const DEFAULT_MODELS: ProviderModel[] = [
  { id: "claude-opus-5", displayName: "Claude Opus 5" },
  { id: "claude-sonnet-5", displayName: "Claude Sonnet 5" },
];

interface ModelsResponse {
  data?: Array<{ id?: unknown; display_name?: unknown }>;
}

export async function listProviderModels(): Promise<ProviderModel[]> {
  const ipcFetch = createIpcFetch();
  const response = await ipcFetch("https://api.anthropic.com/v1/models?limit=100", {
    method: "GET",
    headers: { accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(`모델 목록을 가져오지 못했습니다 (HTTP ${response.status}).`);
  }

  const body = (await response.json()) as ModelsResponse;
  const models: ProviderModel[] = [];
  for (const entry of body.data ?? []) {
    if (typeof entry.id !== "string") continue;
    models.push({
      id: entry.id,
      displayName:
        typeof entry.display_name === "string" && entry.display_name
          ? entry.display_name
          : entry.id,
    });
  }
  if (models.length === 0) {
    throw new Error("이 계정에서 사용할 수 있는 모델이 없습니다.");
  }
  // The API returns newest first; that is also the order worth showing.
  return models;
}
