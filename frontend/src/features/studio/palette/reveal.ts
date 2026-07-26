import type { ActivityView } from '../types';

interface ChromeView {
  activeView: ActivityView;
  sidebarCollapsed: boolean;
  setActiveView: (v: ActivityView) => void;
  toggleSidebar: () => void;
}

/**
 * Make the Manuscript navigator VISIBLE (for a Quick Open resolve). Deliberately NOT
 * `setActiveView('manuscript')`: that has toggle semantics (clicking the active view collapses
 * the sidebar), so resolving a jump while already in Manuscript would hide the navigator the
 * highlight lands in. Switch the view only when off it; otherwise just ensure the sidebar is open.
 */
export function revealManuscript(chrome: ChromeView): void {
  if (chrome.activeView !== 'manuscript') {
    chrome.setActiveView('manuscript'); // switches view + opens the sidebar
  } else if (chrome.sidebarCollapsed) {
    chrome.toggleSidebar(); // already on Manuscript but collapsed → open it (never collapse)
  }
}
