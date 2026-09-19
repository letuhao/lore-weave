import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider, useAuth } from '../auth';

// T11 (plan 2026-09-18, Q4) — the sign-in backfill fires once per SIGN-IN, never per token refresh,
// never on a plain page reload, and a failure never reaches the author.

vi.mock('../api', () => ({
  apiJson: vi.fn().mockRejectedValue(new Error('no network')),
}));

function SignIn() {
  const { setTokens, logoutLocal } = useAuth();
  return (
    <div>
      <button onClick={() => setTokens('tok-signin', 'ref-1')}>login</button>
      <button onClick={logoutLocal}>logout</button>
    </div>
  );
}

const provisionCalls = (f: ReturnType<typeof vi.fn>) =>
  f.mock.calls.filter(([url]) => String(url).endsWith('/v1/books/provision-missing'));

describe('sign-in backfill trigger', () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  beforeEach(() => {
    localStorage.clear();
    fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  const mount = () =>
    render(
      <MemoryRouter>
        <AuthProvider><SignIn /></AuthProvider>
      </MemoryRouter>,
    );

  it('fires ONE provision-missing request with the new bearer on sign-in', () => {
    mount();
    act(() => { screen.getByText('login').click(); });
    const calls = provisionCalls(fetchMock);
    expect(calls).toHaveLength(1);
    const init = calls[0][1] as RequestInit & { headers: Record<string, string> };
    expect(init.method).toBe('POST');
    expect(init.headers.Authorization).toBe('Bearer tok-signin');
    // background housekeeping must not light the global progress bar
    expect(init.headers['X-LW-Operation-Tracked']).toBe('1');
  });

  it('does NOT fire on a silent token refresh, a page reload, or a logout', () => {
    localStorage.setItem('lw_auth', JSON.stringify({ accessToken: 'tok-stored', refreshToken: 'r' }));
    mount(); // a reload with a stored session is not a sign-in
    act(() => {
      localStorage.setItem('lw_auth', JSON.stringify({ accessToken: 'tok-refreshed', refreshToken: 'r2' }));
      window.dispatchEvent(new Event('lw-auth-refreshed'));
    });
    act(() => { screen.getByText('logout').click(); });
    expect(provisionCalls(fetchMock)).toHaveLength(0);
  });

  it('a failing request never throws into sign-in', async () => {
    fetchMock.mockRejectedValue(new Error('network down'));
    mount();
    expect(() => act(() => { screen.getByText('login').click(); })).not.toThrow();
    await act(async () => { await Promise.resolve(); });
    expect(provisionCalls(fetchMock)).toHaveLength(1);
  });
});
