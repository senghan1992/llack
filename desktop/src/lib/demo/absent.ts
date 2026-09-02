/**
 * The demo module, as it exists in every build that is not the demo.
 *
 * `vite.config.ts` aliases `@/lib/demo` to this file. The reason is measurable:
 * `fixture.json` is a 47KB recording, and a static import put it in the desktop
 * app's bundle and the real browser mode's bundle, both of which can never
 * reach it — `isDemoBuild()` is false there, so it was 47KB of provably dead
 * weight the bundler could not drop, because `demoRequest` is referenced.
 *
 * Swapping the module rather than guarding the branch is what makes the demo
 * data structurally absent instead of merely unreachable. It also keeps one
 * honest property: a normal build cannot serve fixture data even if someone
 * later flips a flag by mistake.
 *
 * The exports must match `./index.ts`. They do not have to work.
 */

/** Always false: this file only exists in builds that are not the demo. */
export function isDemoBuild(): boolean {
  return false;
}

/**
 * Never called. `web.ts` reaches this only behind `isDemoBuild()`, so throwing
 * is better than returning something plausible — a silent empty response would
 * make a misconfigured build look merely broken instead of misconfigured.
 */
export async function demoRequest<T>(
  _method: string,
  _path: string,
  _body?: unknown,
): Promise<T> {
  throw new Error("demo runtime is not present in this build");
}

/**
 * A shape, not an account. Only read for the sign-in prefill, which is itself
 * behind `isDemoBuild()`.
 */
export const demoUser = {
  id: "",
  email: "",
  handle: "",
  display_name: "",
} as unknown as import("@/lib/types").User;

export const demoWorkspaceId = "";
