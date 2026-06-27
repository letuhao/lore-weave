import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { apiJson } from '../api';

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

  it('handles unparseable response body', async () => {
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
});
