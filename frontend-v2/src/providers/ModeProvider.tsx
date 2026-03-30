import { createContext, useContext, useMemo, type ReactNode } from 'react';

type Mode = 'workbench' | 'platform';
type ModeCtx = { mode: Mode; isPlatform: boolean; isWorkbench: boolean };

const Ctx = createContext<ModeCtx>({ mode: 'workbench', isPlatform: false, isWorkbench: true });

export function ModeProvider({ children }: { children: ReactNode }) {
  // Read from env or API — default to workbench for self-hosted
  const mode: Mode = (import.meta.env.VITE_LOREWEAVE_MODE as Mode) || 'workbench';

  const value = useMemo(() => ({
    mode,
    isPlatform: mode === 'platform',
    isWorkbench: mode === 'workbench',
  }), [mode]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useMode() {
  return useContext(Ctx);
}
