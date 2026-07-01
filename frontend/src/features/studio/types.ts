// Writing Studio (v2) — shared types.

/** The primary navigators the Activity Bar switches the Side Bar between. */
export type ActivityView = 'manuscript' | 'bible' | 'search' | 'quality';

export const ACTIVITY_VIEWS: readonly ActivityView[] = ['manuscript', 'bible', 'search', 'quality'];

/** Per-book, per-device chrome UI state (which navigator, collapses). Persisted separately
 * from the dockview layout so frame state and dock state can't corrupt each other. */
export interface StudioChromeState {
  activeView: ActivityView;
  sidebarCollapsed: boolean;
  bottomOpen: boolean;
}

export const DEFAULT_CHROME: StudioChromeState = {
  activeView: 'manuscript',
  sidebarCollapsed: false,
  bottomOpen: false,
};
