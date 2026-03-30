import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { apiJson } from '@/api';

type UserProfile = {
  user_id: string;
  email: string;
  display_name: string | null;
  avatar_url: string | null;
};

type AuthState = {
  accessToken: string | null;
  refreshToken: string | null;
  user: UserProfile | null;
  setTokens: (a: string | null, r: string | null) => void;
  logoutLocal: () => void;
};

const Ctx = createContext<AuthState | null>(null);

const AUTH_KEY = 'lw_auth';
const USER_KEY = 'lw_user';

function readToken(key: 'accessToken' | 'refreshToken'): string | null {
  try {
    const raw = localStorage.getItem(AUTH_KEY);
    if (!raw) return null;
    return JSON.parse(raw)[key] ?? null;
  } catch {
    return null;
  }
}

function readUser(): UserProfile | null {
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [accessToken, setAccess] = useState<string | null>(() => readToken('accessToken'));
  const [refreshToken, setRefresh] = useState<string | null>(() => readToken('refreshToken'));
  const [user, setUser] = useState<UserProfile | null>(() => readUser());

  const setTokens = useCallback((a: string | null, r: string | null) => {
    setAccess(a);
    setRefresh(r);
    if (a || r) {
      localStorage.setItem(AUTH_KEY, JSON.stringify({ accessToken: a, refreshToken: r }));
    } else {
      localStorage.removeItem(AUTH_KEY);
      localStorage.removeItem(USER_KEY);
      setUser(null);
    }
  }, []);

  const logoutLocal = useCallback(() => setTokens(null, null), [setTokens]);

  // Fetch user profile when token is available
  useEffect(() => {
    if (!accessToken) return;
    apiJson<UserProfile>('/v1/account/profile', { token: accessToken })
      .then((profile) => {
        setUser(profile);
        localStorage.setItem(USER_KEY, JSON.stringify(profile));
      })
      .catch(() => {
        // 401 is handled by apiJson (auto-logout), other errors just skip
      });
  }, [accessToken]);

  const v = useMemo(
    () => ({ accessToken, refreshToken, user, setTokens, logoutLocal }),
    [accessToken, refreshToken, user, setTokens, logoutLocal],
  );

  return <Ctx.Provider value={v}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const x = useContext(Ctx);
  if (!x) throw new Error('useAuth outside provider');
  return x;
}

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { accessToken } = useAuth();
  const location = useLocation();

  if (!accessToken) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }
  return <>{children}</>;
}
