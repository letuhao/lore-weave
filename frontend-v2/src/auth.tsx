import React, { createContext, useCallback, useContext, useMemo, useState } from 'react';
import { Navigate, useLocation } from 'react-router-dom';

type AuthState = {
  accessToken: string | null;
  refreshToken: string | null;
  setTokens: (a: string | null, r: string | null) => void;
  logoutLocal: () => void;
};

const Ctx = createContext<AuthState | null>(null);

const STORAGE_KEY = 'lw_auth';

function readToken(key: 'accessToken' | 'refreshToken'): string | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw)[key] ?? null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [accessToken, setAccess] = useState<string | null>(() => readToken('accessToken'));
  const [refreshToken, setRefresh] = useState<string | null>(() => readToken('refreshToken'));

  const setTokens = useCallback((a: string | null, r: string | null) => {
    setAccess(a);
    setRefresh(r);
    if (a || r) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ accessToken: a, refreshToken: r }));
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
  }, []);

  const logoutLocal = useCallback(() => setTokens(null, null), [setTokens]);

  const v = useMemo(
    () => ({ accessToken, refreshToken, setTokens, logoutLocal }),
    [accessToken, refreshToken, setTokens, logoutLocal],
  );

  return <Ctx.Provider value={v}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const x = useContext(Ctx);
  if (!x) throw new Error('useAuth outside provider');
  return x;
}

/**
 * Wraps protected routes. Redirects to /login if not authenticated.
 * Saves the current URL so login can redirect back after success.
 */
export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { accessToken } = useAuth();
  const location = useLocation();

  if (!accessToken) {
    // Save where the user wanted to go, so login can redirect back
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }
  return <>{children}</>;
}
