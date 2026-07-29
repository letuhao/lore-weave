// Behaviour of @loreweave/auth-client.
//
// Each test names the failure it would catch. The refresh tests matter most:
// the server ROTATES the refresh token, so the concurrency rules here are not
// style — getting them wrong revokes a live session.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  AUTH_STORAGE_KEY,
  USER_STORAGE_KEY,
  AuthError,
  authedJson,
  clearAuth,
  login,
  logout,
  readTokens,
  readUser,
  refreshAccessToken,
  register,
  writeTokens,
} from '@loreweave/auth-client';

/**
 * An in-memory Storage.
 *
 * NOT gratuitous: the ambient `localStorage` in this runner is Node's
 * experimental Web Storage (it warns `--localstorage-file was provided without
 * a valid path`), not jsdom's — and it has no `clear()`. Depending on it made
 * every test in this file fail on setup. Stubbing gives a deterministic store
 * and keeps the suite honest about what it exercises.
 */
function memoryStorage(): Storage {
  const map = new Map<string, string>();
  return {
    get length() {
      return map.size;
    },
    key: (i: number) => [...map.keys()][i] ?? null,
    getItem: (k: string) => map.get(k) ?? null,
    setItem: (k: string, v: string) => void map.set(k, String(v)),
    removeItem: (k: string) => void map.delete(k),
    clear: () => map.clear(),
  } as Storage;
}

/** Request headers of a recorded `fetch` call. Throws if the call is absent —
 *  a missing call must fail loudly, not silently assert against undefined. */
function headersOf(call: unknown[] | undefined): Record<string, string> {
  if (!call) throw new Error('expected a recorded fetch call, got none');
  return ((call[1] as RequestInit | undefined)?.headers ?? {}) as Record<string, string>;
}

function jsonRes(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

const LOGIN_WIRE = {
  access_token: 'access-1',
  refresh_token: 'refresh-1',
  expires_in_seconds: 900,
  user_profile: { user_id: 'u-1', email: 'a@b.dev', display_name: 'A' },
};

beforeEach(() => {
  vi.restoreAllMocks();
  vi.stubGlobal('localStorage', memoryStorage());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('login', () => {
  it('persists tokens and profile under the shared contract keys', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonRes(LOGIN_WIRE)));

    const result = await login('a@b.dev', 'pw');

    expect(result.accessToken).toBe('access-1');
    // Written where the novel app will also look — this is the SSO handoff.
    expect(readTokens()).toEqual({ accessToken: 'access-1', refreshToken: 'refresh-1' });
    expect(readUser()?.user_id).toBe('u-1');
    expect(localStorage.getItem(AUTH_STORAGE_KEY)).toContain('accessToken');
  });

  it('surfaces the service error CODE, not just a message', async () => {
    // The UI branches on `AUTH_EMAIL_ALREADY_EXISTS` to say "you already have a
    // LoreWeave account". Collapsing errors to a string would kill that.
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonRes({ code: 'AUTH_INVALID_CREDENTIALS', message: 'invalid email or password' }, 401),
      ),
    );

    await expect(login('a@b.dev', 'nope')).rejects.toMatchObject({
      code: 'AUTH_INVALID_CREDENTIALS',
      status: 401,
    });
  });
});

describe('register', () => {
  it('does NOT sign the user in — auth-service returns no tokens', async () => {
    // If this ever "passes" by storing something, the app would render a
    // logged-in shell backed by no token and 401 on everything.
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonRes(
          {
            user_id: 'u-2',
            email: 'new@b.dev',
            email_verified: false,
            created_at: '2026-07-30T00:00:00Z',
            verification_required: true,
          },
          201,
        ),
      ),
    );

    const res = await register({ email: 'new@b.dev', password: 'pw' });

    expect(res.user_id).toBe('u-2');
    expect(readTokens().accessToken).toBeNull();
    expect(localStorage.getItem(AUTH_STORAGE_KEY)).toBeNull();
  });

  it('reports an existing account with its code so the UI can offer sign-in', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          jsonRes({ code: 'AUTH_EMAIL_ALREADY_EXISTS', message: 'email already registered' }, 409),
        ),
    );

    const err = await register({ email: 'novel@b.dev', password: 'pw' }).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(AuthError);
    expect((err as AuthError).code).toBe('AUTH_EMAIL_ALREADY_EXISTS');
  });
});

describe('refreshAccessToken', () => {
  it('is single-flight — concurrent callers share ONE exchange', async () => {
    // The server rotates the refresh token. A second concurrent exchange would
    // present the already-rotated token and revoke the whole session.
    writeTokens({ accessToken: 'old', refreshToken: 'r-1' });
    const f = vi
      .fn()
      .mockResolvedValue(jsonRes({ access_token: 'access-2', refresh_token: 'r-2' }));
    vi.stubGlobal('fetch', f);

    const [a, b, c] = await Promise.all([
      refreshAccessToken(),
      refreshAccessToken(),
      refreshAccessToken(),
    ]);

    expect(f).toHaveBeenCalledTimes(1);
    expect([a, b, c]).toEqual(['access-2', 'access-2', 'access-2']);
    expect(readTokens().refreshToken).toBe('r-2');
  });

  it('does not strand the in-flight slot after the SYNCHRONOUS no-token path', async () => {
    // The finally-after-assignment ordering, and the only shape that can expose
    // it. With no refresh token the IIFE returns WITHOUT awaiting, so its body
    // runs to completion before `refreshInFlight = p`. A `finally` placed
    // INSIDE that body therefore clears the slot BEFORE it is assigned — the
    // assignment then strands a resolved promise, and every later refresh
    // short-circuits to that stale null forever. The user silently stops being
    // able to renew their session.
    //
    // NOTE this needs the sync path. An earlier version of this test awaited a
    // fetch in both refreshes and so never reached the hazard it claimed to
    // guard — it passed against the deliberately broken ordering.
    vi.stubGlobal('fetch', vi.fn());
    expect(await refreshAccessToken()).toBeNull(); // sync path: no token

    // Now a session exists (e.g. the user just logged in, or another tab did).
    writeTokens({ accessToken: 'old', refreshToken: 'r-1' });
    const f = vi
      .fn()
      .mockResolvedValue(jsonRes({ access_token: 'access-2', refresh_token: 'r-2' }));
    vi.stubGlobal('fetch', f);

    expect(await refreshAccessToken()).toBe('access-2');
    expect(f).toHaveBeenCalledTimes(1);
  });

  it('keeps the old refresh token when the server declines to rotate it', async () => {
    writeTokens({ accessToken: 'old', refreshToken: 'r-1' });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonRes({ access_token: 'access-2' })));

    await refreshAccessToken();

    // Dropping it to null here would log the user out on their next 401.
    expect(readTokens()).toEqual({ accessToken: 'access-2', refreshToken: 'r-1' });
  });

  it('returns null with nothing to exchange, and makes no request', async () => {
    const f = vi.fn();
    vi.stubGlobal('fetch', f);

    expect(await refreshAccessToken()).toBeNull();
    expect(f).not.toHaveBeenCalled();
  });
});

describe('authedJson', () => {
  it('silently refreshes and retries once on 401', async () => {
    writeTokens({ accessToken: 'stale', refreshToken: 'r-1' });
    const f = vi
      .fn()
      .mockResolvedValueOnce(jsonRes({ code: 'AUTH_TOKEN_INVALID', message: 'expired' }, 401))
      .mockResolvedValueOnce(jsonRes({ access_token: 'fresh', refresh_token: 'r-2' }))
      .mockResolvedValueOnce(jsonRes({ ok: true }));
    vi.stubGlobal('fetch', f);

    await expect(authedJson<{ ok: boolean }>('/v1/account/profile')).resolves.toEqual({ ok: true });

    // The retry is the THIRD call (original 401 → refresh → retry).
    expect(f).toHaveBeenCalledTimes(3);
    expect(headersOf(f.mock.calls[2]).Authorization).toBe('Bearer fresh');
  });

  it('rides another tab’s newer token instead of logging both apps out', async () => {
    // The multi-tab rotation race. Our refresh fails because `frontend/` (or
    // another tab) already rotated ours away. Logging out here would kick the
    // user out of a session that is perfectly alive.
    writeTokens({ accessToken: 'mine', refreshToken: 'r-old' });
    const f = vi.fn().mockImplementation((url: string) => {
      if (String(url).endsWith('/v1/auth/refresh')) {
        // Simulate the other tab having already stored a working token.
        writeTokens({ accessToken: 'other-tab', refreshToken: 'r-new' });
        return Promise.resolve(jsonRes({ code: 'AUTH_TOKEN_INVALID' }, 401));
      }
      return Promise.resolve(jsonRes({ ok: true }));
    });
    // First call must 401 to trigger the path.
    f.mockResolvedValueOnce(jsonRes({ code: 'AUTH_TOKEN_INVALID' }, 401));
    vi.stubGlobal('fetch', f);

    await expect(authedJson<{ ok: boolean }>('/v1/account/profile')).resolves.toEqual({ ok: true });

    expect(headersOf(f.mock.calls.at(-1)).Authorization).toBe('Bearer other-tab');
  });

  it('never retries the auth endpoints themselves', async () => {
    // A bad login must not spin into a refresh/retry loop.
    writeTokens({ accessToken: 'a', refreshToken: 'r' });
    const f = vi
      .fn()
      .mockResolvedValue(jsonRes({ code: 'AUTH_INVALID_CREDENTIALS', message: 'no' }, 401));
    vi.stubGlobal('fetch', f);

    await expect(authedJson('/v1/auth/login', { method: 'POST' })).rejects.toBeInstanceOf(AuthError);
    expect(f).toHaveBeenCalledTimes(1);
  });
});

describe('clearAuth', () => {
  it('drops both keys and does not navigate', () => {
    // `frontend/`'s forceLogout() hardcodes location.href = '/login', which is
    // wrong for an app mounted at /game/*. This package must stay routing-free.
    writeTokens({ accessToken: 'a', refreshToken: 'r' });
    localStorage.setItem(USER_STORAGE_KEY, JSON.stringify({ user_id: 'u' }));
    const before = window.location.href;

    clearAuth();

    expect(localStorage.getItem(AUTH_STORAGE_KEY)).toBeNull();
    expect(localStorage.getItem(USER_STORAGE_KEY)).toBeNull();
    expect(window.location.href).toBe(before);
  });
});

describe('logout', () => {
  it('REVOKES the session server-side, not just locally', async () => {
    // Clearing localStorage alone only makes this browser forget. The refresh
    // token stays valid in `sessions` until TTL, so a copy of it keeps minting
    // access tokens against an account the user believes they signed out of.
    writeTokens({ accessToken: 'a-1', refreshToken: 'r-1' });
    const f = vi.fn().mockResolvedValue(jsonRes({}, 200));
    vi.stubGlobal('fetch', f);

    await logout();

    expect(f).toHaveBeenCalledTimes(1);
    const [url, init] = f.mock.calls[0] as [string, RequestInit];
    expect(String(url)).toContain('/v1/auth/logout');
    expect(init.method).toBe('POST');
    expect(String(init.body)).toContain('r-1');
    expect(headersOf(f.mock.calls[0]).Authorization).toBe('Bearer a-1');
    expect(readTokens().accessToken).toBeNull();
  });

  it('still clears locally when the revoke call fails', async () => {
    // Offline or gateway down must never leave the user apparently-signed-in.
    writeTokens({ accessToken: 'a-1', refreshToken: 'r-1' });
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));

    await logout();

    expect(readTokens().accessToken).toBeNull();
    expect(readTokens().refreshToken).toBeNull();
  });

  it('makes no request when there is no session to revoke', async () => {
    const f = vi.fn();
    vi.stubGlobal('fetch', f);
    await logout();
    expect(f).not.toHaveBeenCalled();
  });
});
