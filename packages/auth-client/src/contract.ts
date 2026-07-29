// The STORAGE CONTRACT shared with the novel-workflow `frontend/`.
//
// This file is the reason SSO works at all. Both SPAs authenticate against the
// same `auth-service` and the same `loreweave_auth.users` table, so the account
// is already shared server-side — but a *session* is shared only if both apps
// read and write the SAME localStorage keys, in the SAME shape, on the SAME
// origin. localStorage is partitioned per origin: served under one origin (the
// gateway's path-routing, `/app` + `/game`), a login in either app is a login
// in both, for free. Served on two origins, it is two separate sessions.
//
// ⚠ `frontend/` is OUTSIDE the pnpm workspace (pnpm-workspace.yaml — spec §1 #5),
// so it CANNOT import this module. It hardcodes the same literals in
// `frontend/src/api.ts` + `frontend/src/auth.tsx`. That makes this a two-sided
// contract joined by nothing but agreement — exactly the drift shape that
// passes every unit test and dies live. `tests/auth-contract.test.ts` reads
// those two files from disk and reds if either side moves.
//
// Wire shapes come from `services/auth-service/internal/api/handlers.go`.
// NOTE the deliberate asymmetry: the WIRE is snake_case (`access_token`), the
// STORAGE is camelCase (`accessToken`). That is what `frontend/` already
// writes; it is not a style choice we are free to "fix" here.

/** localStorage key holding the token pair. Mirrors `frontend/src/api.ts`. */
export const AUTH_STORAGE_KEY = 'lw_auth';

/** localStorage key holding the cached profile. Mirrors `frontend/src/auth.tsx`. */
export const USER_STORAGE_KEY = 'lw_user';

/**
 * Same-tab notification that a silent refresh wrote new tokens. `storage`
 * events fire only in OTHER tabs, so without this the writing tab keeps its
 * stale in-memory token and 401s against a session it just renewed.
 */
export const AUTH_REFRESHED_EVENT = 'lw-auth-refreshed';

/** Refresh in flight (`detail.active`) — lets a shell show "Reconnecting…". */
export const AUTH_REFRESHING_EVENT = 'lw-auth-refreshing';

/** The token pair AS STORED (camelCase — see the asymmetry note above). */
export interface StoredTokens {
  accessToken: string | null;
  refreshToken: string | null;
}

/** `user_profile` from login + `/v1/account/profile`. */
export interface UserProfile {
  user_id: string;
  email: string;
  display_name?: string | null;
  avatar_url?: string | null;
  email_verified?: boolean;
}

const EMPTY: StoredTokens = { accessToken: null, refreshToken: null };

/** localStorage is absent under SSR and in a bare Node test runner. */
function storage(): Storage | null {
  try {
    return typeof localStorage === 'undefined' ? null : localStorage;
  } catch {
    // A privacy mode can THROW on access rather than return undefined.
    return null;
  }
}

export function readTokens(): StoredTokens {
  const s = storage();
  if (!s) return { ...EMPTY };
  try {
    const raw = s.getItem(AUTH_STORAGE_KEY);
    if (!raw) return { ...EMPTY };
    const parsed = JSON.parse(raw) as Partial<StoredTokens>;
    return {
      accessToken: parsed.accessToken ?? null,
      refreshToken: parsed.refreshToken ?? null,
    };
  } catch {
    return { ...EMPTY };
  }
}

export function writeTokens(tokens: StoredTokens): void {
  const s = storage();
  if (!s) return;
  s.setItem(
    AUTH_STORAGE_KEY,
    JSON.stringify({ accessToken: tokens.accessToken, refreshToken: tokens.refreshToken }),
  );
}

export function readUser(): UserProfile | null {
  const s = storage();
  if (!s) return null;
  try {
    const raw = s.getItem(USER_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as UserProfile) : null;
  } catch {
    return null;
  }
}

export function writeUser(user: UserProfile): void {
  const s = storage();
  if (!s) return;
  s.setItem(USER_STORAGE_KEY, JSON.stringify(user));
}

/**
 * Drop the local session. Deliberately does NOT navigate — `frontend/`'s
 * `forceLogout()` hardcodes `window.location.href = '/login'`, which is wrong
 * for any app not mounted at the root. Under MED-8 path-routing the game lives
 * at `/game/*` and that redirect would throw the player out of the app
 * entirely. Routing is the consumer's decision; this only clears state.
 */
export function clearAuth(): void {
  const s = storage();
  if (!s) return;
  s.removeItem(AUTH_STORAGE_KEY);
  s.removeItem(USER_STORAGE_KEY);
  // Announce it IN THIS TAB. `storage` events fire only in OTHER tabs, so
  // without this a silent 401-driven logout wiped localStorage while React
  // still held the dead token in memory: `isAuthenticated` stayed true, the
  // route guard never redirected, and the user sat in a logged-in-looking shell
  // where every request failed. The explicit signOut() path happened to work
  // because it re-read storage by hand — two ways to clear auth, only one of
  // them telling anybody.
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(AUTH_REFRESHED_EVENT));
  }
}

/**
 * Subscribe to session changes from BOTH directions:
 *   • same tab  — our own silent refresh (`AUTH_REFRESHED_EVENT`)
 *   • other tab — another app/tab on this origin refreshing or logging out
 *                 (`storage`). This is the SSO channel: `frontend/` logging in
 *                 or out is seen here with no coupling between the codebases.
 *
 * `e.key === null` means the whole store was cleared — treat as a change.
 * Returns an unsubscribe function.
 */
export function subscribeAuthChange(onChange: () => void): () => void {
  if (typeof window === 'undefined') return () => {};
  const onStorage = (e: StorageEvent): void => {
    if (e.key === AUTH_STORAGE_KEY || e.key === USER_STORAGE_KEY || e.key === null) onChange();
  };
  window.addEventListener(AUTH_REFRESHED_EVENT, onChange);
  window.addEventListener('storage', onStorage);
  return () => {
    window.removeEventListener(AUTH_REFRESHED_EVENT, onChange);
    window.removeEventListener('storage', onStorage);
  };
}
