import { createContext, useContext, type ReactNode } from 'react';

// K19a.8 — Minimal AuthContext stub for Storybook.
//
// The real `AuthProvider` at `src/auth.tsx` fires a `/v1/me` fetch on
// mount to refresh the user profile. Stories that render components
// using `useAuth()` would trigger that call against the storybook dev
// server (port 6006) and see a 404 flood in the console.
//
// review-impl F1 follow-through: `.storybook/main.ts` aliases `@/auth`
// to THIS module via `viteFinal`, so every import of `useAuth` /
// `AuthProvider` / `RequireAuth` from the canonical path resolves
// here at Storybook build time. That means the mock actually wraps
// real components (not just stories that happen to reach for the
// decorator-level context).
//
// Surface mirrors `src/auth.tsx`:
//   - `AuthProvider({children})` — pre-fills context with fake token + user
//   - `useAuth()` — returns the fake context; throws if called outside
//   - `RequireAuth({children})` — passthrough (stories always "logged in")

interface MockAuth {
  accessToken: string | null;
  refreshToken: string | null;
  user: { id: string; display_name: string; email: string } | null;
  setTokens: (access: string, refresh: string) => void;
  logoutLocal: () => void;
  updateUser: (u: Partial<MockAuth['user']>) => void;
}

const MockAuthCtx = createContext<MockAuth | null>(null);

const value: MockAuth = {
  accessToken: 'storybook-fake-token',
  refreshToken: 'storybook-fake-refresh',
  user: {
    id: '00000000-0000-0000-0000-000000000001',
    display_name: 'Storybook User',
    email: 'storybook@example.local',
  },
  setTokens: () => {},
  logoutLocal: () => {},
  updateUser: () => {},
};

export function AuthProvider({ children }: { children: ReactNode }) {
  return <MockAuthCtx.Provider value={value}>{children}</MockAuthCtx.Provider>;
}

// Back-compat alias: preview.tsx can keep importing `MockAuthProvider`
// explicitly even as the @/auth alias routes real `AuthProvider`
// imports here. Same component, two names.
export const MockAuthProvider = AuthProvider;

export function useAuth() {
  const v = useContext(MockAuthCtx);
  if (!v) {
    throw new Error(
      'Storybook: useAuth called outside AuthProvider. Check preview.tsx decorator wiring.',
    );
  }
  return v;
}

// Matches the real `RequireAuth` signature. In Storybook every story
// is "logged in" via the fake context above, so this is a passthrough.
export function RequireAuth({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
