// Studio Host (#07c / #08 Tier 3) — the registry + StudioContextBus + dock actions, owned
// per-book (R1: remount on book switch; StudioFrame is keyed by bookId, and the ctx useMemo
// re-creates on bookId anyway).
//
// Names + shape match the #08 StudioHostValue contract so #03 Compose / #09 reconciler plug in
// without a refactor. Both stores are external stores read via useSyncExternalStore — NOT context
// state — so a high-frequency bus publish (selection changes) re-renders only opted-in subscribers
// (S4/D21). `subscribe`/`useStudioBusSelector` add SELECTOR granularity so a panel re-renders only
// on the slice it displays. (StudioSessionOrchestrator + StudioEffectReconciler are Tier-3 too but
// deferred to #03/#09.)
import { createContext, useContext, useEffect, useMemo, useRef, useState, type MutableRefObject, type ReactNode } from 'react';
import { useSyncExternalStore } from 'react';
import type { DockviewApi } from 'dockview-react';
import { reflowDockGrid } from '../layout/dockLayout';
import { applyBusEvent, type StudioBusEvent, type StudioBusSnapshot, type StudioStatusBarItem, type StudioToolRegistration } from './types';

interface Store<S> {
  get: () => S;
  set: (next: S) => void;
  subscribe: (l: () => void) => () => void;
}

function createStore<S>(initial: S): Store<S> {
  let snapshot = initial;
  const listeners = new Set<() => void>();
  return {
    get: () => snapshot,
    set: (next: S) => { snapshot = next; listeners.forEach((l) => l()); },
    subscribe: (l: () => void) => { listeners.add(l); return () => { listeners.delete(l); }; },
  };
}

export interface StudioHost {
  bookId: string;
  // Registry (07c) — panels register/unregister; stable across renders.
  registerStudioTool: (reg: StudioToolRegistration) => void;
  unregisterStudioTool: (panelId: string) => void;
  getRegisteredTool: (panelId: string) => StudioToolRegistration | null;
  listRegisteredStudioTools: () => StudioToolRegistration[];
  // Status-bar contributions (#11 F2) — same register/unregister shape as the tool registry.
  registerStatusBarItem: (item: StudioStatusBarItem) => void;
  unregisterStatusBarItem: (id: string) => void;
  // Bus (07c) — publish read-only snapshots; subscribe with an optional selector (S4).
  publish: (event: StudioBusEvent) => void;
  getSnapshot: () => StudioBusSnapshot;
  subscribe: (listener: (s: StudioBusSnapshot) => void, selector?: (s: StudioBusSnapshot) => unknown) => () => void;
  // Dock actions (#08 §StudioHostValue) — the single home for Lane-A ui tools + the palette.
  // `params` (#11 F1) is the deep-link seam: passed to addPanel on open, updateParameters when
  // the panel is already open. Panels read props.params / api.onDidParametersChange.
  // J1: `component` decouples the dock panel id from the catalog component id so ONE component
  // can open per-resource instances (e.g. `json-editor:{docType}:{resourceId}`). Omitted ⇒ the
  // panel id IS the component id (the singleton panels).
  openPanel: (panelId: string, opts?: { focus?: boolean; title?: string; params?: Record<string, unknown>; component?: string }) => void;
  focusManuscriptUnit: (chapterId: string, panelId?: string) => void;
  // Arrange the open dock panels into a cols×rows grid (the layout-preset picker's one seam). Wraps
  // reflowDockGrid so the dock api stays encapsulated; the resulting layout persists via the
  // existing onDidLayoutChange writer. No-op if the dock api isn't ready or <2 panels are open.
  applyDockLayout: (cols: number, rows: number) => void;
  // Internals for the reactive hooks + the dock wiring (not part of the public contract).
  _regStore: Store<StudioToolRegistration[]>;
  _busStore: Store<StudioBusSnapshot>;
  _statusStore: Store<StudioStatusBarItem[]>;
  _dockApiRef: MutableRefObject<DockviewApi | null>;
}

const StudioHostContext = createContext<StudioHost | null>(null);

export function StudioHostProvider({ bookId, children }: { bookId: string; children: ReactNode }) {
  // The dock api arrives after DockviewReact.onReady (StudioDock populates this ref). Created
  // outside the memo so `openPanel` closes over a stable ref, not a per-render value.
  const dockApiRef = useRef<DockviewApi | null>(null);

  const host = useMemo<StudioHost>(() => {
    const regMap = new Map<string, StudioToolRegistration>();
    const regStore = createStore<StudioToolRegistration[]>([]);
    const rebuild = () => regStore.set(Array.from(regMap.values()));
    const busStore = createStore<StudioBusSnapshot>({ revision: 0, bookId, activePanelIds: [] });
    const statusMap = new Map<string, StudioStatusBarItem>();
    const statusStore = createStore<StudioStatusBarItem[]>([]);
    const rebuildStatus = () => statusStore.set(Array.from(statusMap.values()));

    const openPanel = (panelId: string, opts?: { focus?: boolean; title?: string; params?: Record<string, unknown>; component?: string }) => {
      const api = dockApiRef.current;
      if (!api) return;
      const existing = api.getPanel(panelId);
      if (existing) {
        // Already open — deep-link params still land (#11 F1), then focus.
        if (opts?.params) existing.api.updateParameters(opts.params);
        if (opts?.focus !== false) existing.api.setActive();
        return;
      }
      // Title from the caller (catalog), else a live registration, else the id. A CLOSED panel
      // isn't registered yet (registers on mount) so the caller supplies the title.
      const title = opts?.title ?? regMap.get(panelId)?.label ?? panelId;
      // component id must be a built dockview component (STUDIO_PANEL_COMPONENTS); unknown ⇒ no-op.
      // J1: `component` lets a per-resource panel id render the shared component.
      try { api.addPanel({ id: panelId, component: opts?.component ?? panelId, title, params: opts?.params }); }
      catch { /* panel not in the catalog */ }
    };

    return {
      bookId,
      registerStudioTool: (reg) => { regMap.set(reg.panelId, reg); rebuild(); },
      unregisterStudioTool: (panelId) => { if (regMap.delete(panelId)) rebuild(); },
      getRegisteredTool: (panelId) => regMap.get(panelId) ?? null,
      listRegisteredStudioTools: () => regStore.get(),
      registerStatusBarItem: (item) => { statusMap.set(item.id, item); rebuildStatus(); },
      unregisterStatusBarItem: (id) => { if (statusMap.delete(id)) rebuildStatus(); },
      publish: (event) => { busStore.set(applyBusEvent(busStore.get(), event)); },
      getSnapshot: () => busStore.get(),
      subscribe: (listener, selector) => {
        if (!selector) return busStore.subscribe(() => listener(busStore.get()));
        let prev = selector(busStore.get());
        return busStore.subscribe(() => {
          const snap = busStore.get();
          const next = selector(snap);
          if (!Object.is(next, prev)) { prev = next; listener(snap); }
        });
      },
      openPanel,
      focusManuscriptUnit: (chapterId, panelId = 'editor') => {
        // Publish the active chapter to the bus (the Tier-4 ManuscriptUnitProvider watches it and
        // loads the unit) AND open/focus the editor dock panel. The navigator, Quick Open, and the
        // agent's ui_focus_manuscript_unit all drive the editor through this one seam.
        busStore.set(applyBusEvent(busStore.get(), { type: 'chapter', chapterId, bookId }));
        openPanel(panelId);
      },
      applyDockLayout: (cols, rows) => {
        const api = dockApiRef.current;
        if (api) reflowDockGrid(api, cols, rows);
      },
      _regStore: regStore,
      _busStore: busStore,
      _statusStore: statusStore,
      _dockApiRef: dockApiRef,
    };
  }, [bookId]);

  return <StudioHostContext.Provider value={host}>{children}</StudioHostContext.Provider>;
}

/** The imperative host API. Throws outside the provider (a wiring bug, not a runtime path). */
export function useStudioHost(): StudioHost {
  const host = useContext(StudioHostContext);
  if (!host) throw new Error('useStudioHost must be used within a StudioHostProvider');
  return host;
}

/** Null outside the provider instead of throwing — for shared components (e.g. StepConfig,
 * used by both a classic route page AND a studio panel) that must branch behavior rather than
 * assume they're always inside the studio (docs/standards/dockable-gui.md DOCK-7). */
export function useOptionalStudioHost(): StudioHost | null {
  return useContext(StudioHostContext);
}

/** The live list of registered tools (re-renders when a panel (un)registers). */
export function useRegisteredTools(): StudioToolRegistration[] {
  const { _regStore } = useStudioHost();
  return useSyncExternalStore(_regStore.subscribe, _regStore.get);
}

/** The live full bus snapshot (re-renders on every publish). Prefer useStudioBusSelector for a slice. */
export function useStudioBus(): StudioBusSnapshot {
  const { _busStore } = useStudioHost();
  return useSyncExternalStore(_busStore.subscribe, _busStore.get);
}

/** Subscribe to ONE slice of the bus (S4/D21) — re-renders only when the selected value changes,
 * so a chapter-only consumer doesn't re-render on a selection publish. */
export function useStudioBusSelector<T>(selector: (s: StudioBusSnapshot) => T): T {
  const { _busStore } = useStudioHost();
  const selRef = useRef(selector);
  selRef.current = selector;
  const [value, setValue] = useState<T>(() => selector(_busStore.get()));
  useEffect(() => {
    const check = () => {
      const next = selRef.current(_busStore.get());
      setValue((prev) => (Object.is(prev, next) ? prev : next));
    };
    check(); // reconcile anything that changed between render and effect
    return _busStore.subscribe(check);
  }, [_busStore]);
  return value;
}

/** The live sorted status-bar items for one side (#11 F2) — re-renders on (un)register only;
 * item DATA reactivity lives inside each item's own component. */
export function useStatusBarItems(side: StudioStatusBarItem['side']): StudioStatusBarItem[] {
  const { _statusStore } = useStudioHost();
  const all = useSyncExternalStore(_statusStore.subscribe, _statusStore.get);
  return useMemo(
    () => all.filter((i) => i.side === side).sort((a, b) => (a.order ?? 0) - (b.order ?? 0)),
    [all, side],
  );
}

/** Register a status-bar item for the caller's lifetime (mount → register, unmount → unregister).
 * Mirror of useRegisterStudioTool: re-registers only when the id changes. */
export function useRegisterStatusBarItem(item: StudioStatusBarItem): void {
  const { registerStatusBarItem, unregisterStatusBarItem } = useStudioHost();
  const itemRef = useRef(item);
  itemRef.current = item;
  useEffect(() => {
    registerStatusBarItem(itemRef.current);
    return () => unregisterStatusBarItem(itemRef.current.id);
  }, [registerStatusBarItem, unregisterStatusBarItem, item.id]);
}

/** Register a dock tool for this panel's lifetime (mount → register, unmount → unregister).
 * Re-registers only if the panelId changes (a stable panel never churns the registry). */
export function useRegisterStudioTool(reg: StudioToolRegistration): void {
  const { registerStudioTool, unregisterStudioTool } = useStudioHost();
  const regRef = useRef(reg);
  regRef.current = reg;
  useEffect(() => {
    registerStudioTool(regRef.current);
    return () => unregisterStudioTool(regRef.current.panelId);
  }, [registerStudioTool, unregisterStudioTool, reg.panelId]);
}
