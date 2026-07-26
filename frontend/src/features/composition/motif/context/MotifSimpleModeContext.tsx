// W6 §3.3 — the ONE motif context: the simple/expert label toggle. This is a
// PER-DEVICE PREFERENCE, NOT motif data → it follows the CLAUDE.md preference
// rule: read from /v1/me/preferences on mount, write-through on change,
// localStorage as a fast cache only. Default simple=true for a first-run user
// (the beginner persona, §6). A single STABLE context (no per-frame streaming in
// the motif surfaces → do NOT over-split).
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import { loadPrefFromServer, syncPrefsToServer } from '@/lib/syncPrefs';

const PREF_KEY = 'motif_simple_mode';
const LS_KEY = 'loom.motif.simpleMode';

export type MotifSimpleMode = {
  simple: boolean;
  setSimple: (v: boolean) => void;
  toggle: () => void;
};

const Ctx = createContext<MotifSimpleMode | null>(null);

/** Read the cached preference synchronously (localStorage fast-path). Default
 *  true (simple) for a first-run user — the beginner persona is the spec target. */
function readCached(): boolean {
  try {
    const v = localStorage.getItem(LS_KEY);
    if (v === 'true') return true;
    if (v === 'false') return false;
  } catch { /* SSR / disabled storage → default */ }
  return true; // first-run default = simple
}

export function MotifSimpleModeProvider({ token, children }: { token?: string | null; children: ReactNode }) {
  const [simple, setSimpleState] = useState<boolean>(readCached);

  // Hydrate from the server on mount (server is the source of truth; localStorage
  // is only the cache). A miss leaves the cached/default value. This is a
  // synchronization effect (allowed) — NOT event handling.
  useEffect(() => {
    let alive = true;
    loadPrefFromServer<boolean>(PREF_KEY, token).then((server) => {
      if (alive && typeof server === 'boolean') {
        setSimpleState(server);
        try { localStorage.setItem(LS_KEY, String(server)); } catch { /* ignore */ }
      }
    });
    return () => { alive = false; };
  }, [token]);

  const setSimple = useCallback((v: boolean) => {
    setSimpleState(v);
    try { localStorage.setItem(LS_KEY, String(v)); } catch { /* ignore */ }
    syncPrefsToServer(PREF_KEY, v, token);   // write-through (fire-and-forget)
  }, [token]);

  const toggle = useCallback(() => setSimple(!simple), [simple, setSimple]);

  return <Ctx.Provider value={{ simple, setSimple, toggle }}>{children}</Ctx.Provider>;
}

/** Optional — returns a safe default (simple=true, no-op setters) OUTSIDE a
 *  provider, so a motif panel renders standalone (e.g. the existing CompositionPanel
 *  unit test mounts panels without this provider). Mirrors useCriticStateOptional. */
export function useMotifSimpleMode(): MotifSimpleMode {
  const ctx = useContext(Ctx);
  if (ctx) return ctx;
  return { simple: true, setSimple: () => {}, toggle: () => {} };
}
