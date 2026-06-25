// LOOM Composition (T5.4 M1) — the workspace layout model + feature flag.
//
// Owns: the per-device feature flag (default OFF — the fixed sub-tab strip stays
// the default) and the windowing layout (which panels are docked/floated/popped,
// their order + geometry). Both persist to localStorage (a per-device UI state,
// allowed by the persistence rules; server sync is deferred — D-T5.4-SERVER-SYNC).
// The loader VALIDATES the stored layout and falls back to the default dock layout
// on any corruption, so a bad localStorage value can never crash the studio.
import { createContext, useContext, useReducer, useState, useCallback, useEffect, useRef, type ReactNode } from 'react';
import {
  defaultLayout, isValidLayout, type Placement, type Rect, type WorkspaceLayout,
  type WorkspacePanelId,
} from '../workspace/types';

const FLAG_KEY = 'loom.workspace.enabled';
const LAYOUT_KEY = 'loom.workspace.layout';

export type LayoutAction =
  | { type: 'set-active'; id: WorkspacePanelId }
  | { type: 'set-placement'; id: WorkspacePanelId; placement: Placement; rect?: Rect }
  | { type: 'reorder'; ids: WorkspacePanelId[] }
  | { type: 'set-rect'; id: WorkspacePanelId; rect: Rect }
  | { type: 'toggle-hidden'; id: WorkspacePanelId }
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
    case 'reset':
      return defaultLayout();
    default:
      return state;
  }
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
    const parsed = JSON.parse(raw);
    return isValidLayout(parsed) ? parsed : defaultLayout();
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

export function WorkspaceLayoutProvider({ children }: { children: ReactNode }) {
  const [enabled, setEnabledState] = useState<boolean>(loadFlag);
  const [layout, dispatch] = useReducer(reducer, undefined, loadLayout);
  const firstLayout = useRef(true);

  const setEnabled = useCallback((on: boolean) => {
    setEnabledState(on);
    persist(FLAG_KEY, String(on));
  }, []);

  // Persist the layout after every mutation (per-device). Synchronization → useEffect
  // is correct here (NOT event-handling). Skip the initial mount so loading the saved
  // layout doesn't immediately re-write an identical value.
  useEffect(() => {
    if (firstLayout.current) { firstLayout.current = false; return; }
    persist(LAYOUT_KEY, JSON.stringify(layout));
  }, [layout]);

  return (
    <Ctx.Provider value={{ enabled, setEnabled, layout, dispatch }}>{children}</Ctx.Provider>
  );
}

export function useWorkspaceLayout(): WorkspaceCtx {
  const ctx = useContext(Ctx);
  if (ctx === null) throw new Error('useWorkspaceLayout must be used within a WorkspaceLayoutProvider');
  return ctx;
}
