import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { apiJson } from '@/api';

type UserProfile = {
  user_id: string;
  email: string;
  display_name: string | null;
  avatar_url: string | null;
  // Q-GATE: read-only platform flag — gates the public-MCP settings tab.
  public_mcp_enabled?: boolean;
};

type AuthState = {
  accessToken: string | null;
  refreshToken: string | null;
  user: UserProfile | null;
  setTokens: (a: string | null, r: string | null) => void;
  logoutLocal: () => void;
  updateUser: (patch: Partial<UserProfile>) => void;
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

  const updateUser = useCallback((patch: Partial<UserProfile>) => {
    setUser((prev) => {
      if (!prev) return prev;
      const updated = { ...prev, ...patch };
      localStorage.setItem(USER_KEY, JSON.stringify(updated));
      return updated;
    });
  }, []);

  // bug #20: api.ts silently refreshes the access token on a 401 and writes the new pair to
  // localStorage. Re-read it here so React state (and every consumer's `accessToken`) tracks
  // the new token — otherwise components keep sending the stale token and 401 again. The
  // refresh-rotates-the-refresh-token design means stale-token churn would eventually log out.
  useEffect(() => {
    const onRefreshed = () => {
      setAccess(readToken('accessToken'));
      setRefresh(readToken('refreshToken'));
    };
    // Same-tab: api.ts fires this after a silent refresh. Cross-tab: a `storage` event fires in
    // OTHER tabs when this origin's localStorage changes — pick up another tab's refresh (so we
    // send the new token, avoiding our own 401) or its logout (clearing lw_auth → we sign out too).
    const onStorage = (e: StorageEvent) => { if (e.key === AUTH_KEY || e.key === null) onRefreshed(); };
    window.addEventListener('lw-auth-refreshed', onRefreshed);
    window.addEventListener('storage', onStorage);
    return () => {
      window.removeEventListener('lw-auth-refreshed', onRefreshed);
      window.removeEventListener('storage', onStorage);
    };
  }, []);

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
    () => ({ accessToken, refreshToken, user, setTokens, logoutLocal, updateUser }),
    [accessToken, refreshToken, user, setTokens, logoutLocal, updateUser],
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
    // Preserve the FULL location (pathname + search + hash), not just pathname (MB4): a cold
    // deep-link like `/entry/123?sheet=today#note` must survive the login round-trip so a
    // push/feed tap restores the exact tab + sheet, not a stripped path.
    return <Navigate to="/login" state={{ from: location }} replace />;
  }
  return <>{children}</>;
}
