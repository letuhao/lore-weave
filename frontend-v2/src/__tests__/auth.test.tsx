import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { AuthProvider, useAuth, RequireAuth } from '../auth';

// Mock apiJson to avoid real API calls
vi.mock('../api', () => ({
  apiJson: vi.fn().mockRejectedValue(new Error('no network')),
}));

function TestConsumer() {
  const { accessToken, user, setTokens, logoutLocal } = useAuth();
  return (
    <div>
      <span data-testid="token">{accessToken ?? 'none'}</span>
      <span data-testid="user">{user?.display_name ?? 'no-user'}</span>
      <button onClick={() => setTokens('tok-123', 'ref-456')}>login</button>
      <button onClick={logoutLocal}>logout</button>
    </div>
  );
}

describe('AuthProvider', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('starts with no token when localStorage is empty', () => {
    render(
      <MemoryRouter>
        <AuthProvider><TestConsumer /></AuthProvider>
      </MemoryRouter>,
    );
    expect(screen.getByTestId('token').textContent).toBe('none');
  });

  it('reads token from localStorage on mount', () => {
    localStorage.setItem('lw_auth', JSON.stringify({ accessToken: 'saved-tok', refreshToken: 'saved-ref' }));
    render(
      <MemoryRouter>
        <AuthProvider><TestConsumer /></AuthProvider>
      </MemoryRouter>,
    );
    expect(screen.getByTestId('token').textContent).toBe('saved-tok');
  });

  it('setTokens saves to state and localStorage', async () => {
    render(
      <MemoryRouter>
        <AuthProvider><TestConsumer /></AuthProvider>
      </MemoryRouter>,
    );
    await act(async () => {
      screen.getByText('login').click();
    });
    expect(screen.getByTestId('token').textContent).toBe('tok-123');
    const stored = JSON.parse(localStorage.getItem('lw_auth')!);
    expect(stored.accessToken).toBe('tok-123');
    expect(stored.refreshToken).toBe('ref-456');
  });

  it('logoutLocal clears tokens and localStorage', async () => {
    localStorage.setItem('lw_auth', JSON.stringify({ accessToken: 'tok', refreshToken: 'ref' }));
    render(
      <MemoryRouter>
        <AuthProvider><TestConsumer /></AuthProvider>
      </MemoryRouter>,
    );
    await act(async () => {
      screen.getByText('logout').click();
    });
    expect(screen.getByTestId('token').textContent).toBe('none');
    expect(localStorage.getItem('lw_auth')).toBeNull();
  });
});

describe('RequireAuth', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('renders children when authenticated', () => {
    localStorage.setItem('lw_auth', JSON.stringify({ accessToken: 'valid', refreshToken: 'r' }));
    render(
      <MemoryRouter initialEntries={['/protected']}>
        <AuthProvider>
          <Routes>
            <Route path="/protected" element={<RequireAuth><div>secret</div></RequireAuth>} />
            <Route path="/login" element={<div>login page</div>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    );
    expect(screen.getByText('secret')).toBeInTheDocument();
  });

  it('redirects to /login when not authenticated', () => {
    render(
      <MemoryRouter initialEntries={['/protected']}>
        <AuthProvider>
          <Routes>
            <Route path="/protected" element={<RequireAuth><div>secret</div></RequireAuth>} />
            <Route path="/login" element={<div>login page</div>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    );
    expect(screen.getByText('login page')).toBeInTheDocument();
    expect(screen.queryByText('secret')).not.toBeInTheDocument();
  });
});

describe('useAuth outside provider', () => {
  it('throws when used outside AuthProvider', () => {
    function Bad() {
      useAuth();
      return null;
    }
    expect(() => render(<Bad />)).toThrow('useAuth outside provider');
  });
});
