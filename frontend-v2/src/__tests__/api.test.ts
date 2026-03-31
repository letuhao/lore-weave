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
});
