/**
 * The error envelope every command rejects with.
 *
 * Lives apart from `ipc.ts` so both runtimes — the Tauri shell and the browser
 * adapter — can normalise failures without importing each other.
 */

import type { CommandError } from "./types";

/** Narrow an unknown rejection into the error envelope the shell returns. */
export function asCommandError(error: unknown): CommandError {
  if (
    typeof error === "object" &&
    error !== null &&
    "code" in error &&
    "message" in error
  ) {
    return error as CommandError;
  }
  return {
    code: "unknown_error",
    message: typeof error === "string" ? error : "알 수 없는 오류가 발생했습니다.",
    requires_reauth: false,
  };
}

/** Build a rejection with the same shape the Rust side produces. */
export function commandError(
  code: string,
  message: string,
  options: { status?: number; requiresReauth?: boolean } = {},
): CommandError {
  return {
    code,
    message,
    status: options.status ?? null,
    requires_reauth: options.requiresReauth ?? false,
  };
}
