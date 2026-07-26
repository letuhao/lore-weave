import { useCallback, useState } from 'react';
import { useIsMobile } from '@/hooks/useIsMobile';
import { ACTIVITY_VIEWS, DEFAULT_CHROME, clampSidebarWidth, type ActivityView, type StudioChromeState } from '../types';

/**
 * The Writing Studio's frame UI state — which navigator is active, and whether the side bar
 * / bottom panel are open. Per-book, per-device → localStorage (CLAUDE.md: per-device UI
 * state belongs in localStorage, not the server). Kept separate from the dockview layout so
 * a corrupt frame state can't take down the dock and vice-versa.
 */
const chromeKey = (bookId: string) => `lw_studio_chrome_${bookId}`;

// #16 Phase 4 (M6) — a first-time mobile visit has no persisted preference yet; defaulting the
// sidebar OPEN there eats ~300px of a ~390px screen before the dock even starts (confirmed live).
// A returning user's explicit choice (persisted) always wins over this mobile default.
function load(bookId: string, mobileDefault: boolean): StudioChromeState {
  try {
    const raw = localStorage.getItem(chromeKey(bookId));
    if (!raw) return { ...DEFAULT_CHROME, sidebarCollapsed: mobileDefault };
    const parsed = JSON.parse(raw) as Partial<StudioChromeState>;
    return {
      activeView: ACTIVITY_VIEWS.includes(parsed.activeView as ActivityView)
        ? (parsed.activeView as ActivityView)
        : DEFAULT_CHROME.activeView,
      sidebarCollapsed: !!parsed.sidebarCollapsed,
      bottomOpen: !!parsed.bottomOpen,
      sidebarWidth: typeof parsed.sidebarWidth === 'number'
        ? clampSidebarWidth(parsed.sidebarWidth)
        : DEFAULT_CHROME.sidebarWidth,
    };
  } catch {
    return { ...DEFAULT_CHROME, sidebarCollapsed: mobileDefault };
  }
}

export function useStudioChrome(bookId: string) {
  const isMobile = useIsMobile();
  const [state, setState] = useState<StudioChromeState>(() => load(bookId, isMobile));

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

  // Sidebar resize: update width live on every drag frame (persist=false so a mouse-move doesn't
  // hammer localStorage), then persist once on pointer-up / reset (persist=true). Width is always
  // clamped to the allowed range regardless of caller.
  const setSidebarWidth = useCallback((width: number, persist = true) => {
    setState((s) => {
      const next = { ...s, sidebarWidth: clampSidebarWidth(width) };
      if (next.sidebarWidth === s.sidebarWidth) return persist === false ? s : next;
      if (persist) { try { localStorage.setItem(chromeKey(bookId), JSON.stringify(next)); } catch { /* quota */ } }
      return next;
    });
  }, [bookId]);

  return {
    ...state,
    setActiveView,
    toggleSidebar,
    toggleBottom,
    setSidebarWidth,
  };
}
