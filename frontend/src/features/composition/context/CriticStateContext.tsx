// LOOM Composition (WS-B1) — the shared continuity-critic verdict.
//
// The latest generation's critic verdict (coherence/voice/pacing/canon + the C26
// override-gate) + the canon-gate result lived ONLY in ComposeView's local
// `useCritique` mutation state, so a sibling dock panel (the standing `critic`
// SubTab) couldn't read it. This provider — mounted by WorkspaceShell ABOVE the
// windowing layer (like LiveStateProvider) — holds the verdict so a docked/floated
// CriticPanel renders it immediately. A POPPED-OUT panel is a SEPARATE React root
// (this context doesn't cross the window), so the CriticPanel re-fetches by jobId
// there (the locked popout-capable decision).
import { createContext, useContext, useState, useCallback, type ReactNode } from 'react';
import type { Critic, CanonResult } from '../types';

export type CriticVerdict = {
  // The advisory critic (cowrite/auto path). Null on the chapter-assemble path,
  // which produces a canon-gate result but no per-dimension critique.
  critic: Critic;
  canon: CanonResult | null;
  jobId: string | null;
};

type CriticState = {
  verdict: CriticVerdict | null;
  setVerdict: (v: CriticVerdict | null) => void;
};

const CriticStateCtx = createContext<CriticState | null>(null);

export function CriticStateProvider({ children }: { children: ReactNode }) {
  const [verdict, setVerdictRaw] = useState<CriticVerdict | null>(null);
  const setVerdict = useCallback((v: CriticVerdict | null) => setVerdictRaw(v), []);
  return <CriticStateCtx.Provider value={{ verdict, setVerdict }}>{children}</CriticStateCtx.Provider>;
}

/** Optional — returns null outside a provider (e.g. inside a pop-out's own root),
 *  so a consumer can fall back to re-fetching the verdict by jobId. */
export function useCriticStateOptional(): CriticState | null {
  return useContext(CriticStateCtx);
}
