// Stable session context (user + tokens). Per spec §1 #4 + §4 this is the
// SLOW-CHANGING half of client state, deliberately separate from the volatile
// zustand stores so HUD components don't re-render on per-frame churn.
//
// It owns no storage of its own. `@loreweave/auth-client` is the single home of
// the `lw_auth` contract, and that contract is SHARED with the novel-workflow
// `frontend/`. Two consequences worth stating, because they are the whole point:
//
//   1. HYDRATE SYNCHRONOUSLY. The initial state is read from storage in the
//      useState initialiser, not in an effect. A user who is already signed in
//      (possibly from the OTHER app) must never see the login screen flash
//      before the effect runs — and with a route guard, a flash is not cosmetic:
//      it is a redirect to /login and a lost destination.
//
//   2. SUBSCRIBE TO OTHER TABS. `subscribeAuthChange` is the SSO channel. When
//      `frontend/` signs in, refreshes, or signs out on this origin, the game
//      follows without either codebase importing the other.
//
// Same-origin is the precondition for both: localStorage is partitioned per
// origin. Under MED-8 path-routing (/app + /game behind the gateway) this is
// free; across two dev ports it is two separate sessions.

import { createContext, use, useCallback, useEffect, useMemo, useState } from 'react';
import type { ReactNode, JSX } from 'react';
import {
  logout as clearStoredAuth,
  readTokens,
  readUser,
  subscribeAuthChange,
  type UserProfile,
} from '@loreweave/auth-client';

export interface Session {
  user: UserProfile | null;
  accessToken: string | null;
  /** Bound PC for the active reality. Null until onboarding binds one. */
  characterId: string | null;
}

interface SessionContextValue extends Session {
  isAuthenticated: boolean;
  /** Re-read storage. Call after a login/refresh writes new tokens. */
  syncFromStorage: () => void;
  setCharacterId: (id: string | null) => void;
  signOut: () => void;
}

const SessionContext = createContext<SessionContextValue | null>(null);

function snapshot(): Pick<Session, 'user' | 'accessToken'> {
  return { user: readUser(), accessToken: readTokens().accessToken };
}

export function SessionProvider({ children }: { children: ReactNode }): JSX.Element {
  const [auth, setAuth] = useState(snapshot);
  const [characterId, setCharacterId] = useState<string | null>(null);
  const { user, accessToken } = auth;

  const syncFromStorage = useCallback(() => setAuth(snapshot()), []);

  // Synchronisation with an external store — the correct use of useEffect
  // (subscribe + cleanup), not event handling.
  useEffect(() => subscribeAuthChange(syncFromStorage), [syncFromStorage]);

  const signOut = useCallback(() => {
    // `logout()` revokes the session server-side before clearing storage, and
    // clears locally even if that call fails. Fire-and-forget: the local state
    // must drop immediately, not after a network round-trip.
    void clearStoredAuth();
    setCharacterId(null);
    // The clear also emits the same-tab auth event, but reflect it here too so
    // sign-out is synchronous for this tab's render.
    syncFromStorage();
  }, [syncFromStorage]);

  const value = useMemo<SessionContextValue>(
    () => ({
      user,
      accessToken,
      characterId,
      isAuthenticated: !!accessToken,
      syncFromStorage,
      setCharacterId,
      signOut,
    }),
    [user, accessToken, characterId, syncFromStorage, signOut],
  );

  // React 19 renders a context object directly as its provider.
  return <SessionContext value={value}>{children}</SessionContext>;
}

export function useSession(): SessionContextValue {
  const ctx = use(SessionContext);
  if (!ctx) throw new Error('useSession must be used within <SessionProvider>');
  return ctx;
}
