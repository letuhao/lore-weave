import React, { createContext, useCallback, useContext, useMemo, useState } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { apiJson } from '@/api';

type UserProfile = {
  user_id: string;
  email: string;
  display_name: string | null;
};

type AuthState = {
  accessToken: string | null;
  // T4d: the ORIGINAL user (HS256) access token, kept alongside the admin RS256
  // token. The admin CRUD/confirm endpoints want the RS256 `accessToken`; the
  // chat-service message stream wants this HS256 bearer for `get_current_user`
  // (admin authority then rides the separate X-Admin-Token header). Null for a
  // session stored before this field existed (re-login repopulates it).
  userToken: string | null;
  user: UserProfile | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
};

const Ctx = createContext<AuthState | null>(null);

// CMS-specific key — deliberately NOT the main app's `lw_auth`, so the two
// apps can be open side by side without clobbering each other's session.
const AUTH_KEY = 'cms_auth';

type Stored = { accessToken: string | null; userToken: string | null; user: UserProfile | null };

function readStored(): Stored {
  try {
    const raw = localStorage.getItem(AUTH_KEY);
    if (!raw) return { accessToken: null, userToken: null, user: null };
    const parsed = JSON.parse(raw) as Stored;
    return {
      accessToken: parsed.accessToken ?? null,
      userToken: parsed.userToken ?? null,
      user: parsed.user ?? null,
    };
  } catch {
    return { accessToken: null, userToken: null, user: null };
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [{ accessToken, userToken, user }, setState] = useState<Stored>(() => readStored());

  const persist = useCallback((next: Stored) => {
    setState(next);
    if (next.accessToken) {
      localStorage.setItem(AUTH_KEY, JSON.stringify(next));
    } else {
      localStorage.removeItem(AUTH_KEY);
    }
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const res = await apiJson<{
        access_token: string;
        user?: UserProfile;
      }>('/v1/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      });
      // The entire CMS calls admin-only endpoints, so we immediately exchange the
      // user token for an RS256 admin session (auth-service /v1/admin/session) and
      // store THAT as the working token. A non-admin account 403s here — surface it
      // as a clear login failure rather than a broken session.
      let adminToken: string;
      try {
        const sess = await apiJson<{ token: string }>('/v1/admin/session', {
          method: 'POST',
          token: res.access_token,
        });
        adminToken = sess.token;
      } catch {
        throw new Error('This account does not have admin access.');
      }
      // Keep BOTH: the admin RS256 token (working token for admin endpoints) and
      // the original user HS256 token (the chat-service stream bearer, T4d).
      persist({ accessToken: adminToken, userToken: res.access_token, user: res.user ?? null });
    },
    [persist],
  );

  const logout = useCallback(
    () => persist({ accessToken: null, userToken: null, user: null }),
    [persist],
  );

  const v = useMemo(
    () => ({ accessToken, userToken, user, login, logout }),
    [accessToken, userToken, user, login, logout],
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
