import { createContext, useContext, useMemo, useState, type ReactNode } from 'react';

/**
 * The as-of (story-time) state shared across the temporal surfaces. The TimeSlider WRITES the
 * current chapter ordinal; the canonical card / change timeline / diff READ it. `asOf === undefined`
 * means "current head" (latest-valid) — the default, byte-identical to a non-temporal read.
 *
 * Split from the data hooks so the slider re-render (every drag tick) doesn't thrash the whole
 * panel — only the consuming surfaces that read `asOf` re-query.
 */
interface AsOfState {
  /** Current chapter ordinal, or undefined for the head. */
  asOf: number | undefined;
  setAsOf: (ordinal: number | undefined) => void;
}

const AsOfCtx = createContext<AsOfState | null>(null);

export function AsOfProvider({ children, initialAsOf }: { children: ReactNode; initialAsOf?: number }) {
  const [asOf, setAsOf] = useState<number | undefined>(initialAsOf);
  const value = useMemo(() => ({ asOf, setAsOf }), [asOf]);
  return <AsOfCtx.Provider value={value}>{children}</AsOfCtx.Provider>;
}

export function useAsOf(): AsOfState {
  const ctx = useContext(AsOfCtx);
  if (!ctx) throw new Error('useAsOf must be used within an AsOfProvider');
  return ctx;
}
