import { useCallback, useState } from 'react';
import { ACTIVITY_VIEWS, DEFAULT_CHROME, type ActivityView, type StudioChromeState } from '../types';

/**
 * The Writing Studio's frame UI state — which navigator is active, and whether the side bar
 * / bottom panel are open. Per-book, per-device → localStorage (CLAUDE.md: per-device UI
 * state belongs in localStorage, not the server). Kept separate from the dockview layout so
 * a corrupt frame state can't take down the dock and vice-versa.
 */
const chromeKey = (bookId: string) => `lw_studio_chrome_${bookId}`;

function load(bookId: string): StudioChromeState {
  try {
    const raw = localStorage.getItem(chromeKey(bookId));
    if (!raw) return DEFAULT_CHROME;
    const parsed = JSON.parse(raw) as Partial<StudioChromeState>;
    return {
      activeView: ACTIVITY_VIEWS.includes(parsed.activeView as ActivityView)
        ? (parsed.activeView as ActivityView)
        : DEFAULT_CHROME.activeView,
      sidebarCollapsed: !!parsed.sidebarCollapsed,
      bottomOpen: !!parsed.bottomOpen,
    };
  } catch {
    return DEFAULT_CHROME;
  }
}

export function useStudioChrome(bookId: string) {
  const [state, setState] = useState<StudioChromeState>(() => load(bookId));

  const setActiveView = useCallback((activeView: ActivityView) => {
    setState((s) => {
      // Clicking the already-active navigator toggles the side bar (VS Code behaviour).
      const next = s.activeView === activeView && !s.sidebarCollapsed
        ? { ...s, sidebarCollapsed: true }
        : { ...s, activeView, sidebarCollapsed: false };
      try { localStorage.setItem(chromeKey(bookId), JSON.stringify(next)); } catch { /* quota */ }
      return next;
    });
  }, [bookId]);

  const toggleSidebar = useCallback(() => {
    setState((s) => {
      const next = { ...s, sidebarCollapsed: !s.sidebarCollapsed };
      try { localStorage.setItem(chromeKey(bookId), JSON.stringify(next)); } catch { /* quota */ }
      return next;
    });
  }, [bookId]);

  const toggleBottom = useCallback(() => {
    setState((s) => {
      const next = { ...s, bottomOpen: !s.bottomOpen };
      try { localStorage.setItem(chromeKey(bookId), JSON.stringify(next)); } catch { /* quota */ }
      return next;
    });
  }, [bookId]);

  return {
    ...state,
    setActiveView,
    toggleSidebar,
    toggleBottom,
  };
}
