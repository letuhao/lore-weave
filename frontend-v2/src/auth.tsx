import React, { createContext, useContext, useMemo, useState } from 'react';

type AuthState = {
  accessToken: string | null;
  refreshToken: string | null;
  setTokens: (a: string | null, r: string | null) => void;
  logoutLocal: () => void;
};

const Ctx = createContext<AuthState | null>(null);

const STORAGE_KEY = 'lw_auth';

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [accessToken, setAccess] = useState<string | null>(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return null;
      const j = JSON.parse(raw);
      return j.accessToken ?? null;
    } catch {
      return null;
    }
  });
  const [refreshToken, setRefresh] = useState<string | null>(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return null;
      const j = JSON.parse(raw);
      return j.refreshToken ?? null;
    } catch {
      return null;
    }
  });

  const setTokens = (a: string | null, r: string | null) => {
    setAccess(a);
    setRefresh(r);
    if (a || r) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ accessToken: a, refreshToken: r }));
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
  };

  const logoutLocal = () => setTokens(null, null);

  const v = useMemo(
    () => ({ accessToken, refreshToken, setTokens, logoutLocal }),
    [accessToken, refreshToken],
  );

  return <Ctx.Provider value={v}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const x = useContext(Ctx);
  if (!x) throw new Error('useAuth outside provider');
  return x;
}
