// LOOM Composition (T5.4 M1) — the workspace layout model + feature flag.
//
// Owns: the per-device feature flag (default OFF — the fixed sub-tab strip stays
// the default) and the windowing layout (which panels are docked/floated/popped,
// their order + geometry). Both persist to localStorage (a per-device UI state,
// allowed by the persistence rules; server sync is deferred — D-T5.4-SERVER-SYNC).
// The loader VALIDATES the stored layout and falls back to the default dock layout
// on any corruption, so a bad localStorage value can never crash the studio.
import { createContext, useContext, useReducer, useState, useCallback, useEffect, useRef, type ReactNode } from 'react';
import { loadPrefFromServer, syncPrefsToServer } from '@/lib/syncPrefs';
import {
  defaultLayout, isValidLayout, type Placement, type Rect, type WorkspaceLayout,
  type WorkspacePanelId,
} from '../workspace/types';

const FLAG_KEY = 'loom.workspace.enabled';
const LAYOUT_KEY = 'loom.workspace.layout';
// WS-D (D-T5.4-SERVER-SYNC) — the server-prefs key holding {enabled, layout} so the
// workspace arrangement follows the user across devices. localStorage stays the
// per-device fast cache (instant paint); the server is LWW source of truth on login.
const PREF_KEY = 'loom_workspace';
const SYNC_DEBOUNCE_MS = 800;

type LoomWorkspacePref = { enabled?: boolean; layout?: unknown };

export type LayoutAction =
  | { type: 'set-active'; id: WorkspacePanelId }
  | { type: 'set-placement'; id: WorkspacePanelId; placement: Placement; rect?: Rect }
  | { type: 'reorder'; ids: WorkspacePanelId[] }
  | { type: 'set-rect'; id: WorkspacePanelId; rect: Rect }
  | { type: 'toggle-hidden'; id: WorkspacePanelId }
  | { type: 'hydrate'; layout: WorkspaceLayout }
  | { type: 'reset' };

function reducer(state: WorkspaceLayout, action: LayoutAction): WorkspaceLayout {
  switch (action.type) {
    case 'set-active':
      return { ...state, active: action.id };
    case 'set-placement': {
      const cur = state.panels[action.id] ?? { placement: 'dock', order: 0 };
      return { ...state, panels: { ...state.panels, [action.id]: { ...cur, placement: action.placement, rect: action.rect ?? cur.rect } } };
    }
    case 'reorder': {
      const panels = { ...state.panels };
      action.ids.forEach((id, i) => {
        const cur = panels[id] ?? { placement: 'dock' as Placement, order: i };
        panels[id] = { ...cur, order: i };
      });
      return { ...state, panels };
    }
    case 'set-rect': {
      const cur = state.panels[action.id] ?? { placement: 'float' as Placement, order: 0 };
      return { ...state, panels: { ...state.panels, [action.id]: { ...cur, rect: action.rect } } };
    }
    case 'toggle-hidden': {
      const cur = state.panels[action.id] ?? { placement: 'dock' as Placement, order: 0 };
      return { ...state, panels: { ...state.panels, [action.id]: { ...cur, hidden: !cur.hidden } } };
    }
    case 'hydrate':
      return action.layout;
    case 'reset':
      return defaultLayout();
    default:
      return state;
  }
}

/** Validate + forward-merge a parsed layout over the current default (so a layout
 *  saved before a panel existed still gets that panel's dock entry). Shared by the
 *  localStorage loader and the server-pref hydrate. */
function mergeLayout(parsed: unknown): WorkspaceLayout {
  if (!isValidLayout(parsed)) return defaultLayout();
  const def = defaultLayout();
  const p = parsed as WorkspaceLayout;
  return { ...def, ...p, panels: { ...def.panels, ...p.panels } };
}

function loadFlag(): boolean {
  try {
    return localStorage.getItem(FLAG_KEY) === 'true';
  } catch {
    return false;
  }
}

function loadLayout(): WorkspaceLayout {
  try {
    const raw = localStorage.getItem(LAYOUT_KEY);
    if (!raw) return defaultLayout();
    // Forward-compat: a layout saved BEFORE a panel existed (e.g. pre-T3.6
    // 'references') won't list it — merge over the default so every CURRENT panel
    // always has a dock entry (else new panels are unreachable for returning users).
    return mergeLayout(JSON.parse(raw));
  } catch {
    return defaultLayout();   // corrupt / unparseable → default (never crash)
  }
}

function persist(key: string, value: string) {
  try { localStorage.setItem(key, value); } catch { /* private mode / quota — ignore */ }
}

type WorkspaceCtx = {
  enabled: boolean;
  setEnabled: (on: boolean) => void;
  layout: WorkspaceLayout;
  dispatch: (action: LayoutAction) => void;
};

const Ctx = createContext<WorkspaceCtx | null>(null);

export function WorkspaceLayoutProvider({ token, children }: { token?: string | null; children: ReactNode }) {
  const [enabled, setEnabledState] = useState<boolean>(loadFlag);
  const [layout, dispatch] = useReducer(reducer, undefined, loadLayout);
  const firstLayout = useRef(true);

  // WS-D server-sync refs: latest values for the debounced write-through + the
  // last value known to the server (echo-guard so a hydrate doesn't write itself back).
  const tokenRef = useRef(token);
  tokenRef.current = token;
  const enabledRef = useRef(enabled);
  enabledRef.current = enabled;
  const layoutRef = useRef(layout);
  layoutRef.current = layout;
  const lastSyncedRef = useRef<string>('');
  const syncTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Debounced, fire-and-forget write-through of {enabled, layout} (LWW). No-op without
  // a token or when nothing changed since the last sync/hydrate.
  const pushPref = useCallback(() => {
    const tk = tokenRef.current;
    if (!tk) return;
    const payload: LoomWorkspacePref = { enabled: enabledRef.current, layout: layoutRef.current };
    const json = JSON.stringify(payload);
    if (json === lastSyncedRef.current) return;
    lastSyncedRef.current = json;
    if (syncTimer.current) clearTimeout(syncTimer.current);
    syncTimer.current = setTimeout(() => syncPrefsToServer(PREF_KEY, payload, tk), SYNC_DEBOUNCE_MS);
  }, []);

  const setEnabled = useCallback((on: boolean) => {
    enabledRef.current = on;            // keep the ref current for the immediate pushPref
    setEnabledState(on);
    persist(FLAG_KEY, String(on));      // per-device cache stays instant
    pushPref();                         // write-through (LWW)
  }, [pushPref]);

  // Hydrate from the server on login (opt-in/additive — localStorage already painted
  // synchronously above). LWW: the server value wins on load, then local changes
  // write through. Forward-merge the server layout so missing panels stay reachable.
  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    void loadPrefFromServer<LoomWorkspacePref>(PREF_KEY, token).then((pref) => {
      if (cancelled || !pref) return;
      // Server-wins-on-load (LWW): cancel any pending write-through armed by a user
      // change made BEFORE this hydrate resolved — otherwise that stale timer would
      // fire AFTER hydrate and POST a value contradicting the just-hydrated state
      // (silent server/local divergence). The pre-hydrate change is discarded by design.
      if (syncTimer.current) { clearTimeout(syncTimer.current); syncTimer.current = null; }
      const nextEnabled = typeof pref.enabled === 'boolean' ? pref.enabled : enabledRef.current;
      if (typeof pref.enabled === 'boolean') { setEnabledState(pref.enabled); persist(FLAG_KEY, String(pref.enabled)); }
      let nextLayout = layoutRef.current;
      if (pref.layout !== undefined) {
        nextLayout = mergeLayout(pref.layout);
        dispatch({ type: 'hydrate', layout: nextLayout });
        persist(LAYOUT_KEY, JSON.stringify(nextLayout));
      }
      // Mark the hydrated value as server-known so the resulting persist effect /
      // setEnabled don't echo it straight back.
      lastSyncedRef.current = JSON.stringify({ enabled: nextEnabled, layout: nextLayout });
    });
    return () => { cancelled = true; };
  }, [token]);

  // Persist the layout after every mutation (per-device localStorage, instant) +
  // write through to the server (debounced). Synchronization → useEffect is correct
  // here. Skip the initial mount so loading the saved layout doesn't re-write it.
  useEffect(() => {
    if (firstLayout.current) { firstLayout.current = false; return; }
    persist(LAYOUT_KEY, JSON.stringify(layout));
    pushPref();
  }, [layout, pushPref]);

  // Flush any pending debounced sync on unmount.
  useEffect(() => () => { if (syncTimer.current) clearTimeout(syncTimer.current); }, []);

  return (
    <Ctx.Provider value={{ enabled, setEnabled, layout, dispatch }}>{children}</Ctx.Provider>
  );
}

export function useWorkspaceLayout(): WorkspaceCtx {
  const ctx = useContext(Ctx);
  if (ctx === null) throw new Error('useWorkspaceLayout must be used within a WorkspaceLayoutProvider');
  return ctx;
}

/** Non-throwing accessor — returns null when there is no provider. CompositionPanel
 *  uses this so it still renders (the fixed-strip fallback) when mounted WITHOUT a
 *  WorkspaceShell (e.g. in unit tests / the flag-OFF path where the windowing host
 *  isn't required). The dock components use the throwing `useWorkspaceLayout`. */
export function useWorkspaceLayoutOptional(): WorkspaceCtx | null {
  return useContext(Ctx);
}
