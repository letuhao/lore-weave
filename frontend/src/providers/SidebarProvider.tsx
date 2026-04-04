import { createContext, useCallback, useContext, useState, type ReactNode } from 'react';

type SidebarState = {
  collapsed: boolean;
  toggle: () => void;
};

const Ctx = createContext<SidebarState | null>(null);

const STORAGE_KEY = 'lw_sidebar_collapsed';

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'true';
  } catch {
    return false;
  }
}

export function SidebarProvider({ children }: { children: ReactNode }) {
  const [collapsed, setCollapsed] = useState(readCollapsed);

  const toggle = useCallback(() => {
    setCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem(STORAGE_KEY, String(next));
      return next;
    });
  }, []);

  return <Ctx.Provider value={{ collapsed, toggle }}>{children}</Ctx.Provider>;
}

export function useSidebar() {
  const x = useContext(Ctx);
  if (!x) throw new Error('useSidebar outside provider');
  return x;
}
