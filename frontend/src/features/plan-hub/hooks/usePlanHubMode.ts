// Plan Hub view mode — SIMPLE (a linear chapter list, content-first, the default for a new writer)
// vs ADVANCED (the lane/arc/scene canvas, for plotters). A 3-persona user panel scored the canvas
// Easy 2/5 — jargon-heavy and containers-first — so Simple is the default, Advanced is opt-in.
//
// This is a PER-USER PREFERENCE, not plan data → it follows the CLAUDE.md preference rule and mirrors
// the shipped MotifSimpleMode exactly: read from /v1/me/preferences on mount, write-through on
// change, localStorage as a fast cache only, server is the source of truth. Default simple=true.
import { useCallback, useEffect, useState } from 'react';
import { loadPrefFromServer, syncPrefsToServer } from '@/lib/syncPrefs';

const PREF_KEY = 'plan_hub_mode_simple';
const LS_KEY = 'planHub.mode.simple';

export interface PlanHubMode {
  simple: boolean;
  setSimple: (v: boolean) => void;
  toggle: () => void;
}

/** localStorage fast-path; default true (Simple) for a first-run writer — the panel's easy-to-use fix. */
function readCached(): boolean {
  try {
    const v = localStorage.getItem(LS_KEY);
    if (v === 'true') return true;
    if (v === 'false') return false;
  } catch { /* disabled storage → default */ }
  return true;
}

export function usePlanHubMode(token: string | null): PlanHubMode {
  const [simple, setSimpleState] = useState<boolean>(readCached);

  // Hydrate from the server (source of truth); a miss keeps the cached/default. Synchronization
  // effect (allowed) — not event handling.
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
    syncPrefsToServer(PREF_KEY, v, token); // write-through, fire-and-forget
  }, [token]);

  return { simple, setSimple, toggle: useCallback(() => setSimple(!simple), [simple, setSimple]) };
}
