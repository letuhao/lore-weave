// @loreweave/auth-client — the auth surface for `frontend-game`.
//
// Talks to `auth-service` THROUGH `api-gateway-bff` (the gateway proxies
// /v1/auth + /v1/account — see gateway-setup.ts). Bearer JWT, no cookies:
// auth-service returns the token pair in the JSON body and sets no cookie at
// all (there is no `Set-Cookie` anywhere in that service). The frontend-game
// architecture spec §8 describes a cookie session — that description does NOT
// match the code, and this client follows the code.
//
// Storage lives in ./contract — shared, byte-for-byte, with `frontend/`.

export {
  AUTH_STORAGE_KEY,
  USER_STORAGE_KEY,
  AUTH_REFRESHED_EVENT,
  AUTH_REFRESHING_EVENT,
  readTokens,
  writeTokens,
  readUser,
  writeUser,
  clearAuth,
  subscribeAuthChange,
  type StoredTokens,
  type UserProfile,
} from './contract';

import {
  AUTH_REFRESHED_EVENT,
  AUTH_REFRESHING_EVENT,
  clearAuth,
  readTokens,
  writeTokens,
  writeUser,
  type UserProfile,
} from './contract';

/**
 * Base URL. Default '' = relative/same-origin, which rides the proxy→gateway
 * path in both environments (vite `/v1` proxy in dev, nginx in prod). Keep it
 * relative: an absolute `http://localhost:3000` is the gateway's CONTAINER
 * port, unreachable from a browser — the exact rot that silently broke eight
 * call-sites in `frontend/`.
 */
export function apiBase(): string {
  const env = (import.meta as { env?: { VITE_API_BASE?: string } }).env;
  return env?.VITE_API_BASE || '';
}

/** `{code, message}` — auth-service's `writeErr` envelope (util.go). */
export class AuthError extends Error {
  readonly code: string;
  readonly status: number;
  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = 'AuthError';
    this.code = code;
    this.status = status;
  }
}

async function parseError(res: Response): Promise<AuthError> {
  let code = 'AUTH_UNKNOWN';
  let message = res.statusText || 'request failed';
  try {
    const body = (await res.json()) as { code?: string; message?: string };
    if (body.code) code = body.code;
    if (body.message) message = body.message;
  } catch {
    // Non-JSON (a proxy error page). Keep the status-derived message.
  }
  return new AuthError(code, message, res.status);
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${apiBase()}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw await parseError(res);
  return (await res.json()) as T;
}

// ── wire shapes (snake_case — handlers.go) ──────────────────────────────

interface LoginWire {
  access_token: string;
  refresh_token: string;
  expires_in_seconds: number;
  user_profile: UserProfile;
}

export interface RegisterResult {
  user_id: string;
  email: string;
  email_verified: boolean;
  created_at: string;
  /** True when SMTP is configured; a verification mail was sent. */
  verification_required: boolean;
}

export interface LoginResult {
  accessToken: string;
  refreshToken: string;
  expiresInSeconds: number;
  user: UserProfile;
}

// ── operations ─────────────────────────────────────────────────────────

/**
 * Create an account. **Does NOT sign you in** — auth-service's register
 * returns a profile with no tokens, so the caller must follow with `login()`.
 * Throws `AUTH_EMAIL_ALREADY_EXISTS` (409) when the address is taken — which
 * for a novel-app user is not really an error but the SSO signal: they already
 * have a LoreWeave account and should log in instead.
 */
export function register(input: {
  email: string;
  password: string;
  display_name?: string;
  locale?: string;
}): Promise<RegisterResult> {
  return postJson<RegisterResult>('/v1/auth/register', input);
}

/** Sign in and persist the session. Throws `AUTH_INVALID_CREDENTIALS` (401). */
export async function login(email: string, password: string): Promise<LoginResult> {
  const wire = await postJson<LoginWire>('/v1/auth/login', { email, password });
  writeTokens({ accessToken: wire.access_token, refreshToken: wire.refresh_token });
  writeUser(wire.user_profile);
  return {
    accessToken: wire.access_token,
    refreshToken: wire.refresh_token,
    expiresInSeconds: wire.expires_in_seconds,
    user: wire.user_profile,
  };
}

/**
 * Ask for a reset mail.
 *
 * ALWAYS resolves — auth-service answers 202 whether or not the address exists,
 * on purpose. Surfacing "no such account" here would turn this endpoint into an
 * account-enumeration oracle, so the UI must say the same thing either way.
 * Treat a rejection as a transport failure, never as "unknown email".
 */
export async function requestPasswordReset(email: string): Promise<void> {
  const res = await fetch(`${apiBase()}/v1/auth/password-reset/request`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: email.trim() }),
  });
  // 202 is the only success. A 4xx/5xx here is infrastructure, not a verdict
  // about the address.
  if (!res.ok) throw await parseError(res);
}

/**
 * Consume a reset token and set the new password.
 *
 * Throws `AUTH_RESET_TOKEN_INVALID` for expired / already-used / unknown tokens
 * AND for a password that fails policy — the server collapses both into one
 * code, which is why the client validates the password itself first (see
 * `checkPassword`); otherwise a weak password reads as "your link expired".
 */
export async function confirmPasswordReset(token: string, newPassword: string): Promise<void> {
  const res = await fetch(`${apiBase()}/v1/auth/password-reset/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token: token.trim(), new_password: newPassword }),
  });
  if (!res.ok) throw await parseError(res);
}

/**
 * Sign out. REVOKES THE SESSION SERVER-SIDE, then clears local storage.
 *
 * Clearing localStorage alone is not a logout — it only makes this browser
 * forget. The refresh token stays valid in `sessions` until its TTL, so anyone
 * holding a copy keeps minting access tokens against an account the user
 * believes they signed out of. `/v1/auth/logout` is what actually kills it.
 *
 * The local clear happens regardless: a failed or offline revoke must never
 * leave the user apparently-still-signed-in on this device. Best-effort remote,
 * unconditional local — in that order.
 */
export async function logout(): Promise<void> {
  const { refreshToken, accessToken } = readTokens();
  try {
    if (refreshToken) {
      await fetch(`${apiBase()}/v1/auth/logout`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
    }
  } catch {
    // Offline / gateway down. Fall through — the local clear still runs.
  }
  clearAuth();
}

/**
 * The server's password policy, mirrored for immediate feedback.
 *
 * `auth-service` is authoritative (`validPassword`, util.go: min length + at
 * least one letter + at least one digit). This copy exists ONLY so a user gets
 * told what is wrong before a round-trip — the server's 400 says
 * "invalid email or password policy" without saying which half failed or why.
 * Pinned against the Go source by `tests/auth-contract.test.ts` so the two
 * cannot drift into telling the user different things.
 */
export const PASSWORD_MIN_LENGTH = 8;

export type PasswordProblem = 'too_short' | 'needs_letter' | 'needs_digit';

/** Returns the unmet requirements, empty when the password satisfies policy. */
export function checkPassword(pw: string): PasswordProblem[] {
  const problems: PasswordProblem[] = [];
  if (pw.length < PASSWORD_MIN_LENGTH) problems.push('too_short');
  // Unicode-aware, matching Go's `unicode.IsLetter`/`IsDigit` — an ASCII-only
  // [a-z]/[0-9] test would reject a valid password containing only non-Latin
  // letters that the server happily accepts.
  if (!/\p{L}/u.test(pw)) problems.push('needs_letter');
  if (!/\p{Nd}/u.test(pw)) problems.push('needs_digit');
  return problems;
}

function emit(name: string, detail?: unknown): void {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(name, detail === undefined ? undefined : { detail }));
}

// Single-flight refresh. The server ROTATES the refresh token, so two
// concurrent 401s must share ONE exchange — otherwise the second presents an
// already-rotated token and the whole session is revoked.
let refreshInFlight: Promise<string | null> | null = null;

/**
 * Exchange the refresh token for a fresh access token. Returns null when there
 * is nothing to exchange or the server refuses. Also exported for long-lived
 * streams (SSE/WS) that must refresh proactively — no fetch 401 ever fires
 * there to trigger it.
 */
export function refreshAccessToken(): Promise<string | null> {
  if (refreshInFlight) return refreshInFlight;

  // Only announce when there is actually a token to exchange; a logged-out
  // miss is not "reconnecting".
  const announce = !!readTokens().refreshToken;
  if (announce) emit(AUTH_REFRESHING_EVENT, { active: true });

  const p = (async (): Promise<string | null> => {
    try {
      const { refreshToken } = readTokens();
      if (!refreshToken) return null;
      const res = await fetch(`${apiBase()}/v1/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!res.ok) return null;
      const data = (await res.json()) as { access_token?: string; refresh_token?: string };
      if (!data.access_token) return null;
      // Keep the old refresh token if the server declines to rotate it.
      writeTokens({
        accessToken: data.access_token,
        refreshToken: data.refresh_token ?? refreshToken,
      });
      emit(AUTH_REFRESHED_EVENT);
      return data.access_token;
    } catch {
      return null;
    }
  })();

  refreshInFlight = p;
  // Clear AFTER the assignment. Doing it in the IIFE's own `finally` would run
  // BEFORE this line on a synchronous path, leaking a resolved promise that
  // short-circuits every later refresh forever.
  void p.finally(() => {
    if (refreshInFlight === p) refreshInFlight = null;
    if (announce) emit(AUTH_REFRESHING_EVENT, { active: false });
  });
  return p;
}

/**
 * Authenticated JSON fetch with silent-refresh + ONE retry.
 *
 * `onSessionLost` fires when the session cannot be recovered. The caller
 * routes; this package never navigates (see `clearAuth`).
 */
export async function authedJson<T>(
  path: string,
  init: RequestInit & { token?: string | null } = {},
  opts: { onSessionLost?: () => void } = {},
  retried = false,
): Promise<T> {
  const token = init.token ?? readTokens().accessToken;
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init.headers as Record<string, string> | undefined),
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${apiBase()}${path}`, { ...init, headers });
  if (res.status === 204) return undefined as T;

  if (!res.ok) {
    // Never retry the auth endpoints themselves — a bad login must not loop.
    if (res.status === 401 && token && !path.startsWith('/v1/auth/') && !retried) {
      const fresh = await refreshAccessToken();
      if (fresh) return authedJson<T>(path, { ...init, token: fresh }, opts, true);

      // Multi-tab rotation race: our refresh may have failed because ANOTHER
      // tab (or `frontend/`) refreshed first and rotated ours away. If storage
      // now holds a DIFFERENT access token, that tab already recovered the
      // session — ride it instead of logging the user out of both apps.
      const current = readTokens().accessToken;
      if (current && current !== token) {
        return authedJson<T>(path, { ...init, token: current }, opts, true);
      }
    }
    if (res.status === 401) {
      clearAuth();
      opts.onSessionLost?.();
    }
    throw await parseError(res);
  }

  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

/** Current user from the server (the token's authority, not the cache). */
export async function me(opts: { onSessionLost?: () => void } = {}): Promise<UserProfile> {
  const profile = await authedJson<UserProfile>('/v1/account/profile', {}, opts);
  writeUser(profile);
  return profile;
}
