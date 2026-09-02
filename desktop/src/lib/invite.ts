/**
 * The invite token's journey through the web client.
 *
 * An invite link looks like `https://llack.example.com/?invite=<token>`. The
 * person clicking it is by definition not signed in yet, so the token cannot
 * be spent on arrival — it is parked in sessionStorage, survives the sign-in
 * or sign-up round trip, and is redeemed the moment the workspace list first
 * loads. sessionStorage rather than localStorage: an invite is a one-shot
 * errand for this tab, not durable account state.
 *
 * The `?invite=` parameter is stripped from the address bar immediately, so a
 * copied or bookmarked URL does not carry a live token around.
 */

const KEY = "llack.pending-invite";

/** Call once at startup, before anything reads `location.search`. */
export function captureInviteFromLocation(): void {
  const params = new URLSearchParams(window.location.search);
  const token = params.get("invite");
  if (!token) return;
  try {
    window.sessionStorage.setItem(KEY, token);
  } catch {
    // Blocked storage: the capture is lost, but so would the session be.
  }
  params.delete("invite");
  const query = params.toString();
  window.history.replaceState(
    null,
    "",
    window.location.pathname + (query ? `?${query}` : ""),
  );
}

export function pendingInviteToken(): string | null {
  try {
    return window.sessionStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function clearPendingInvite(): void {
  try {
    window.sessionStorage.removeItem(KEY);
  } catch {
    // Nothing to clear if nothing could be stored.
  }
}

/**
 * The web-clickable form of a server-issued invite URL.
 *
 * The server mints `llack://invite?token=…` for the desktop deep link; a
 * browser cannot open that, so the settings screen shows this instead.
 */
export function webInviteUrl(inviteUrl: string | null | undefined): string | null {
  if (!inviteUrl) return null;
  const match = /[?&]token=([^&]+)/.exec(inviteUrl);
  if (!match?.[1]) return null;
  return `${window.location.origin}/?invite=${match[1]}`;
}
