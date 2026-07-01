// Studio Host (#07c) — the registry + StudioContextBus, owned per-book (R1: remount on book
// switch; StudioFrame is keyed by bookId, and the ctx useMemo re-creates on bookId anyway).
//
// Both are external stores (refs + listener sets) read via useSyncExternalStore, NOT context
// state — so a high-frequency bus publish (selection changes) re-renders only opted-in
// subscribers, never every panel that merely holds the imperative API (D4 / "split by update
// frequency").
import { createContext, useContext, useEffect, useMemo, useRef, type ReactNode } from 'react';
import { useSyncExternalStore } from 'react';
import { applyBusEvent, type StudioBusEvent, type StudioBusSnapshot, type StudioToolRegistration } from './types';

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
  // Registry (imperative — panels register/unregister; stable across renders).
  register: (reg: StudioToolRegistration) => void;
  unregister: (panelId: string) => void;
  getTool: (panelId: string) => StudioToolRegistration | null;
  listTools: () => StudioToolRegistration[];
  // Bus (imperative).
  publish: (event: StudioBusEvent) => void;
  getBusSnapshot: () => StudioBusSnapshot;
  // Internal stores for the reactive hooks below.
  _regStore: Store<StudioToolRegistration[]>;
  _busStore: Store<StudioBusSnapshot>;
}

const StudioHostContext = createContext<StudioHost | null>(null);

export function StudioHostProvider({ bookId, children }: { bookId: string; children: ReactNode }) {
  const host = useMemo<StudioHost>(() => {
    const regMap = new Map<string, StudioToolRegistration>();
    const regStore = createStore<StudioToolRegistration[]>([]);
    const rebuild = () => regStore.set(Array.from(regMap.values()));
    const busStore = createStore<StudioBusSnapshot>({ revision: 0, bookId, activePanelIds: [] });

    return {
      register: (reg) => { regMap.set(reg.panelId, reg); rebuild(); },
      unregister: (panelId) => { if (regMap.delete(panelId)) rebuild(); },
      getTool: (panelId) => regMap.get(panelId) ?? null,
      listTools: () => regStore.get(),
      publish: (event) => { busStore.set(applyBusEvent(busStore.get(), event)); },
      getBusSnapshot: () => busStore.get(),
      _regStore: regStore,
      _busStore: busStore,
    };
  }, [bookId]);

  return <StudioHostContext.Provider value={host}>{children}</StudioHostContext.Provider>;
}

/** The imperative host API. Throws if used outside the provider (a wiring bug, not a runtime path). */
export function useStudioHost(): StudioHost {
  const host = useContext(StudioHostContext);
  if (!host) throw new Error('useStudioHost must be used within a StudioHostProvider');
  return host;
}

/** The live list of registered tools (re-renders when a panel (un)registers). */
export function useRegisteredTools(): StudioToolRegistration[] {
  const { _regStore } = useStudioHost();
  return useSyncExternalStore(_regStore.subscribe, _regStore.get);
}

/** The live bus snapshot (re-renders on publish). Opt-in — most consumers use the imperative API. */
export function useStudioBus(): StudioBusSnapshot {
  const { _busStore } = useStudioHost();
  return useSyncExternalStore(_busStore.subscribe, _busStore.get);
}

/** Register a dock tool for this panel's lifetime (mount → register, unmount → unregister).
 * Re-registers only if the panelId changes (a stable panel never churns the registry). */
export function useRegisterStudioTool(reg: StudioToolRegistration): void {
  const { register, unregister } = useStudioHost();
  const regRef = useRef(reg);
  regRef.current = reg;
  useEffect(() => {
    register(regRef.current);
    return () => unregister(regRef.current.panelId);
  }, [register, unregister, reg.panelId]);
}
