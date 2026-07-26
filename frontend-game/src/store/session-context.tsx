// React Context for stable session data (user id, character id, jwt).
// Per spec §1 #4 + §4: stable context — changes rarely, separate from
// volatile zustand stores so HUD components don't re-render on per-frame
// state churn.

import { createContext, useContext, useMemo, useState, type ReactNode } from 'react';
import type { JSX } from 'react';

export interface Session {
  userId: string;
  characterId: string | null;
  jwt: string | null;
}

interface SessionContextValue {
  session: Session;
  setSession: (s: Session) => void;
  clear: () => void;
}

const SessionContext = createContext<SessionContextValue | null>(null);

const EMPTY_SESSION: Session = { userId: '', characterId: null, jwt: null };

export function SessionProvider({ children }: { children: ReactNode }): JSX.Element {
  const [session, setSession] = useState<Session>(EMPTY_SESSION);
  const value = useMemo(
    () => ({ session, setSession, clear: () => setSession(EMPTY_SESSION) }),
    [session],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error('useSession must be used within <SessionProvider>');
  return ctx;
}
