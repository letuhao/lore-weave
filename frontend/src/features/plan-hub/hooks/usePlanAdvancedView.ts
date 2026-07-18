// Plan Hub — the ADVANCED sub-view: GRAPH (the React Flow canvas — zoom, pan, drag-to-move, scene
// links; the right tool for a structure too large to scroll) vs LANE (the readable lane-flow layout,
// the 2026-07-18 mockup redesign — wrapping cards, no zoom). BOTH are structure-first "Advanced"; a
// writer picks the one that fits the job, and it persists.
//
// Default GRAPH: dropping the canvas's free zoom/pan/drag was a capability regression a user flagged
// as critical ("when the graph extends so huge, it can zoom in/out and move freely"), so the navigable
// canvas is the default and the readable Lane view is one persistent click away.
//
// PER-USER PREFERENCE (CLAUDE.md rule; mirrors usePlanHubMode / MotifSimpleMode): server is the source
// of truth (/v1/me/preferences), localStorage is a fast cache, write-through on change.
import { useCallback, useEffect, useState } from 'react';
import { loadPrefFromServer, syncPrefsToServer } from '@/lib/syncPrefs';

const PREF_KEY = 'plan_hub_advanced_graph';
const LS_KEY = 'planHub.advanced.graph';

export interface PlanAdvancedView {
  /** true ⇒ the React Flow graph (zoom/pan/drag); false ⇒ the lane-flow view. */
  graph: boolean;
  setGraph: (v: boolean) => void;
}

function readCached(): boolean {
  try {
    const v = localStorage.getItem(LS_KEY);
    if (v === 'true') return true;
    if (v === 'false') return false;
  } catch { /* disabled storage → default */ }
  return true; // default: the navigable graph
}

export function usePlanAdvancedView(token: string | null): PlanAdvancedView {
  const [graph, setGraphState] = useState<boolean>(readCached);

  useEffect(() => {
    let alive = true;
    loadPrefFromServer<boolean>(PREF_KEY, token).then((server) => {
      if (alive && typeof server === 'boolean') {
        setGraphState(server);
        try { localStorage.setItem(LS_KEY, String(server)); } catch { /* ignore */ }
      }
    });
    return () => { alive = false; };
  }, [token]);

  const setGraph = useCallback((v: boolean) => {
    setGraphState(v);
    try { localStorage.setItem(LS_KEY, String(v)); } catch { /* ignore */ }
    syncPrefsToServer(PREF_KEY, v, token);
  }, [token]);

  return { graph, setGraph };
}
