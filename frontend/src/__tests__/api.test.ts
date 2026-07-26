import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { apiJson, refreshAccessToken } from '../api';

// Mock import.meta.env
vi.stubEnv('VITE_API_BASE', '');

describe('apiJson', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  function mockFetch(status: number, body: unknown, headers?: Record<string, string>) {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: status >= 200 && status < 300,
      status,
      statusText: 'Error',
      text: () => Promise.resolve(body != null ? JSON.stringify(body) : ''),
      headers: new Headers(headers),
    });
  }

  it('makes a GET request and returns parsed JSON', async () => {
    mockFetch(200, { id: 1, name: 'Test' });
    const result = await apiJson<{ id: number; name: string }>('/v1/test');
    expect(result).toEqual({ id: 1, name: 'Test' });
    expect(globalThis.fetch).toHaveBeenCalledWith('/v1/test', expect.objectContaining({
      headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
    }));
  });

  it('includes Authorization header when token is provided', async () => {
    mockFetch(200, { ok: true });
    await apiJson('/v1/test', { token: 'my-jwt' });
    expect(globalThis.fetch).toHaveBeenCalledWith('/v1/test', expect.objectContaining({
      headers: expect.objectContaining({ Authorization: 'Bearer my-jwt' }),
    }));
  });

  it('returns undefined for 204 No Content', async () => {
    mockFetch(204, null);
    const result = await apiJson('/v1/test', { method: 'DELETE' });
    expect(result).toBeUndefined();
  });

  it('throws an error with message for non-ok responses', async () => {
    mockFetch(400, { code: 'VALIDATION_ERROR', message: 'Bad input' });
    await expect(apiJson('/v1/test')).rejects.toThrow('Bad input');
  });

  it('throws with statusText when body has no message', async () => {
    mockFetch(500, {});
    await expect(apiJson('/v1/test')).rejects.toThrow('Error');
  });

  // D-CHAT-COMPACT-ERROR-SWALLOWED — every Python/FastAPI service (chat-service
  // included) returns {detail: ...}, not {code, message}; without this fallback
  // every such error silently rendered as the useless statusText instead (e.g.
  // compact's clean 409 "nothing to compact" showed as "Conflict").
  it('throws with the FastAPI detail string when body has no message', async () => {
    mockFetch(409, { detail: 'nothing to compact' });
    await expect(apiJson('/v1/test')).rejects.toThrow('nothing to compact');
  });

  it('joins a FastAPI 422 validation-error detail array', async () => {
    mockFetch(422, { detail: [{ loc: ['body', 'name'], msg: 'field required', type: 'missing' }] });
    await expect(apiJson('/v1/test')).rejects.toThrow('field required');
  });

  // /review-impl (2026-07-09) MED — the first cut only handled string/array
  // `detail`, missing composition-service's `{code: "action_error"}` and
  // campaign-service's `{code, message}` object shapes, which fell straight
  // through to the same useless statusText this fix was meant to kill.
  it('reads {message} off an object-shaped detail (campaign-service shape)', async () => {
    mockFetch(404, { detail: { code: 'CAMPAIGN_NOT_FOUND', message: 'Not found' } });
    await expect(apiJson('/v1/test')).rejects.toThrow('Not found');
  });

  it('falls back to {code} when an object-shaped detail has no message (composition-service shape)', async () => {
    mockFetch(400, { detail: { code: 'action_error' } });
    await expect(apiJson('/v1/test')).rejects.toThrow('action_error');
  });

  it('prefers {message} over {detail} when a body somehow has both', async () => {
    mockFetch(400, { message: 'the real message', detail: 'ignored' });
    await expect(apiJson('/v1/test')).rejects.toThrow('the real message');
  });

  it('handles unparseable response body', async () => {
    // A SHORT plain-text body is a real message — Go's `http.Error(w, "…", 500)` writes
    // text/plain and 24 such sites exist across the Go services. Keep surfacing it.
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
      text: () => Promise.resolve('not json'),
    });
    await expect(apiJson('/v1/test')).rejects.toThrow('not json');
  });

  it('on 401 with token, clears localStorage and redirects', async () => {
    localStorage.setItem('lw_auth', 'something');
    // Mock window.location
    const originalHref = window.location.href;
    Object.defineProperty(window, 'location', {
      writable: true,
      value: { ...window.location, href: originalHref },
    });

    mockFetch(401, { code: 'UNAUTHORIZED', message: 'Token expired' });
    await apiJson('/v1/test', { token: 'expired-token' });
    expect(localStorage.getItem('lw_auth')).toBeNull();
    expect(window.location.href).toBe('/login');
  });

  it('sends POST with body', async () => {
    mockFetch(201, { id: 42 });
    const result = await apiJson<{ id: number }>('/v1/test', {
      method: 'POST',
      body: JSON.stringify({ name: 'New' }),
    });
    expect(result).toEqual({ id: 42 });
  });

  // ── bug #20: silent access-token refresh ──

  function jsonOk(body: unknown) {
    return { ok: true, status: 200, statusText: 'OK', text: () => Promise.resolve(JSON.stringify(body)), json: () => Promise.resolve(body), headers: new Headers() };
  }
  function unauthorized() {
    return { ok: false, status: 401, statusText: 'Unauthorized', text: () => Promise.resolve(JSON.stringify({ message: 'expired' })), json: () => Promise.resolve({}), headers: new Headers() };
  }

  it('on 401, silently refreshes the token and retries the original request', async () => {
    localStorage.setItem('lw_auth', JSON.stringify({ accessToken: 'old', refreshToken: 'r0' }));
    const seen: Record<string, number> = {};
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.endsWith('/v1/auth/refresh')) return Promise.resolve(jsonOk({ access_token: 'new', refresh_token: 'r1' }));
      seen[url] = (seen[url] ?? 0) + 1;
      return Promise.resolve(seen[url] === 1 ? unauthorized() : jsonOk({ data: 'ok' }));
    });

    const result = await apiJson('/v1/protected', { token: 'old' });
    expect(result).toEqual({ data: 'ok' });
    // retried with the NEW token, and the rotated pair persisted
    expect(globalThis.fetch).toHaveBeenCalledWith('/v1/protected', expect.objectContaining({
      headers: expect.objectContaining({ Authorization: 'Bearer new' }),
    }));
    expect(JSON.parse(localStorage.getItem('lw_auth')!)).toEqual({ accessToken: 'new', refreshToken: 'r1' });
  });

  it('shares ONE refresh across concurrent 401s (single-flight)', async () => {
    localStorage.setItem('lw_auth', JSON.stringify({ accessToken: 'old', refreshToken: 'r0' }));
    let refreshCalls = 0;
    const seen: Record<string, number> = {};
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.endsWith('/v1/auth/refresh')) { refreshCalls++; return Promise.resolve(jsonOk({ access_token: 'new', refresh_token: 'r1' })); }
      seen[url] = (seen[url] ?? 0) + 1;
      return Promise.resolve(seen[url] === 1 ? unauthorized() : jsonOk({ url }));
    });

    const [a, b] = await Promise.all([
      apiJson('/v1/a', { token: 'old' }),
      apiJson('/v1/b', { token: 'old' }),
    ]);
    expect(refreshCalls).toBe(1); // both 401s shared one refresh (refresh rotation requires this)
    expect(a).toEqual({ url: '/v1/a' });
    expect(b).toEqual({ url: '/v1/b' });
  });

  it('logs out when the refresh itself fails', async () => {
    localStorage.setItem('lw_auth', JSON.stringify({ accessToken: 'old', refreshToken: 'r0' }));
    Object.defineProperty(window, 'location', { writable: true, value: { href: '' } });
    globalThis.fetch = vi.fn().mockResolvedValue(unauthorized()); // every call (incl. refresh) 401s

    await apiJson('/v1/protected', { token: 'old' });
    expect(localStorage.getItem('lw_auth')).toBeNull();
    expect(window.location.href).toBe('/login');
  });

  it('multi-tab: recovers via another tab’s rotated token instead of logging out', async () => {
    // Another tab already refreshed (rotating our refresh token): localStorage holds a NEW
    // access token, but this request used the stale React-state token. Our own refresh fails
    // (revoked refresh token), but we must retry with the localStorage token, NOT log out.
    localStorage.setItem('lw_auth', JSON.stringify({ accessToken: 'fromOtherTab', refreshToken: 'r1' }));
    Object.defineProperty(window, 'location', { writable: true, value: { href: '' } });
    const seen: Record<string, number> = {};
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.endsWith('/v1/auth/refresh')) return Promise.resolve(unauthorized()); // our refresh fails
      seen[url] = (seen[url] ?? 0) + 1;
      return Promise.resolve(seen[url] === 1 ? unauthorized() : jsonOk({ data: 'recovered' }));
    });

    const result = await apiJson('/v1/protected', { token: 'stale' });
    expect(result).toEqual({ data: 'recovered' });
    expect(globalThis.fetch).toHaveBeenCalledWith('/v1/protected', expect.objectContaining({
      headers: expect.objectContaining({ Authorization: 'Bearer fromOtherTab' }),
    }));
    expect(localStorage.getItem('lw_auth')).not.toBeNull(); // did NOT log out
    expect(window.location.href).toBe(''); // no redirect
  });

  it('logs out if even the freshly-refreshed token is rejected (retried 401)', async () => {
    localStorage.setItem('lw_auth', JSON.stringify({ accessToken: 'old', refreshToken: 'r0' }));
    Object.defineProperty(window, 'location', { writable: true, value: { href: '' } });
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.endsWith('/v1/auth/refresh')) return Promise.resolve(jsonOk({ access_token: 'new', refresh_token: 'r1' }));
      return Promise.resolve(unauthorized()); // /v1/protected 401s even with the new token
    });

    await apiJson('/v1/protected', { token: 'old' });
    expect(localStorage.getItem('lw_auth')).toBeNull();
    expect(window.location.href).toBe('/login');
  });

  // — a NON-JSON error body is infra noise, never a user-facing message (S2's live 502) —

  function mockRawFetch(status: number, text: string, statusText = 'Bad Gateway') {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status,
      statusText,
      text: () => Promise.resolve(text),
      headers: new Headers(),
    });
  }

  const NGINX_502 =
    '<html>\r\n<head><title>502 Bad Gateway</title></head>\r\n<body>\r\n' +
    '<center><h1>502 Bad Gateway</h1></center>\r\n<hr><center>nginx</center>\r\n</body>\r\n</html>\r\n';

  it('never surfaces an HTML error page as the message (the raw-502-in-a-toast bug)', async () => {
    mockRawFetch(502, NGINX_502);
    const err = await apiJson('/v1/composition/works/x').catch((e) => e as Error);
    // readBackendError feeds Error.message + body.message to the global MutationCache toast,
    // so an HTML document reaching EITHER renders markup at the author.
    expect(err.message).toBe('Bad Gateway');
    expect(err.message).not.toContain('<html');
    expect((err as Error & { body?: { message?: unknown } }).body?.message).toBeUndefined();
  });

  it('keeps the raw non-JSON body for debugging, just not as the message', async () => {
    mockRawFetch(502, NGINX_502);
    const err = await apiJson('/v1/x').catch((e) => e as Error);
    const body = (err as Error & { body?: { code?: string; rawBody?: string } }).body;
    expect(body?.code).toBe('PARSE_ERROR');
    expect(body?.rawBody).toContain('502 Bad Gateway');
  });

  it('still surfaces a Go http.Error plain-text message (the fix must not swallow those)', async () => {
    // services/agent-registry-service/internal/api/oauth.go:146 — http.Error(w, "database
    // unavailable", 503). Suppressing ALL non-JSON bodies would have regressed 24 such sites
    // to a bare "Service Unavailable".
    mockRawFetch(503, 'database unavailable', 'Service Unavailable');
    const err = await apiJson('/v1/x').catch((e) => e as Error);
    expect(err.message).toBe('database unavailable');
  });

  it('suppresses a long non-JSON body even without markup (a dumped page/stack, not a sentence)', async () => {
    mockRawFetch(500, 'x'.repeat(500), 'Internal Server Error');
    const err = await apiJson('/v1/x').catch((e) => e as Error);
    expect(err.message).toBe('Internal Server Error');
  });

  it('falls back to the status code when statusText is empty (HTTP/2 drops the reason phrase)', async () => {
    // Needs a body that yields NO message (the HTML page) AND an empty statusText — behind an
    // HTTP/2 load balancer both are true at once, and Error('') would render a BLANK toast: a
    // silent failure, the exact thing the §2 bar forbids.
    mockRawFetch(504, NGINX_502, '');
    const err = await apiJson('/v1/x').catch((e) => e as Error);
    expect(err.message).toBe('HTTP 504');
  });

  it('still surfaces a real JSON envelope message (the fix must not swallow those)', async () => {
    mockFetch(409, { detail: 'nothing to compact' });
    const err = await apiJson('/v1/chat/compact').catch((e) => e as Error);
    expect(err.message).toBe('nothing to compact');
  });

  // M4 (F1) — a real silent refresh announces itself so the shell can show "Reconnecting…".
  describe('refreshAccessToken reconnecting signal', () => {
    const originalFetch2 = globalThis.fetch;
    beforeEach(() => { localStorage.clear(); vi.restoreAllMocks(); });
    afterEach(() => { globalThis.fetch = originalFetch2; });

    function captureRefreshing(): boolean[] {
      const seen: boolean[] = [];
      window.addEventListener('lw-auth-refreshing', (e) => seen.push(Boolean((e as CustomEvent).detail?.active)));
      return seen;
    }

    it('dispatches active:true then active:false around a real refresh', async () => {
      localStorage.setItem('lw_auth', JSON.stringify({ accessToken: 'old', refreshToken: 'r0' }));
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true, status: 200, statusText: 'OK', headers: new Headers(),
        text: () => Promise.resolve(JSON.stringify({ access_token: 'new', refresh_token: 'r1' })),
        json: () => Promise.resolve({ access_token: 'new', refresh_token: 'r1' }),
      });
      const seen = captureRefreshing();
      const tok = await refreshAccessToken();
      expect(tok).toBe('new');
      expect(seen).toEqual([true, false]); // reconnecting shown, then cleared
    });

    it('does NOT announce when there is no refresh token (a logged-out miss is not "reconnecting")', async () => {
      // no lw_auth in storage
      const seen = captureRefreshing();
      const tok = await refreshAccessToken();
      expect(tok).toBeNull();
      expect(seen).toEqual([]); // never showed the chip
    });
  });
});
