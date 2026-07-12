// Writing Studio (v2) — shared types.

/** The primary navigators the Activity Bar switches the Side Bar between. */
export type ActivityView = 'manuscript' | 'plan' | 'bible' | 'search' | 'quality';

// 24 PH25 — `plan` sits next to `manuscript`: they are the two densities of the book (the spec
// tree and the prose spine), and the rail's click contract distinguishes them (plan → the Hub
// canvas; manuscript → the Editor).
export const ACTIVITY_VIEWS: readonly ActivityView[] = ['manuscript', 'plan', 'bible', 'search', 'quality'];

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
