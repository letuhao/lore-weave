// LOOM Composition (T5.4) — workspace windowing types.
// The studio's 19 panels can be placed in a dock rail, an in-app floating window,
// or a popped-out OS window. The layout is per-device (localStorage); live state
// (co-writer/chat SSE, Tiptap) is hoisted ABOVE this layer so a placement change
// re-parents a panel's host without remounting it (the no-remount invariant).

// The addressable studio panels (mirrors CompositionPanel's SubTab union, minus the
// conditional 'threads' which is gated separately).
export type WorkspacePanelId =
  | 'compose' | 'cowriter' | 'assemble' | 'planner' | 'beats' | 'graph' | 'cast'
  | 'relmap' | 'timeline' | 'arc' | 'worldmap' | 'grounding' | 'references'
  | 'style' | 'canon' | 'critic' | 'threads' | 'progress' | 'quality' | 'flywheel' | 'settings';

const PANEL_IDS: WorkspacePanelId[] = [
  'compose', 'cowriter', 'assemble', 'planner', 'beats', 'graph', 'cast', 'relmap',
  'timeline', 'arc', 'worldmap', 'grounding', 'references', 'style', 'canon', 'critic',
  'threads', 'progress', 'quality', 'flywheel', 'settings',
];

/** Narrow an untrusted string (e.g. a popout URL param) to a known panel id. */
export function isWorkspacePanelId(v: string): v is WorkspacePanelId {
  return (PANEL_IDS as string[]).includes(v);
}

export type Placement = 'dock' | 'float' | 'popout';

export type Rect = { x: number; y: number; w: number; h: number };

export type PanelState = {
  placement: Placement;
  order: number;        // dock order (ignored when floated/popped)
  hidden?: boolean;     // docked-but-collapsed (still MOUNTED — CSS hidden)
  rect?: Rect;          // float/popout geometry
};

export type WorkspaceLayout = {
  version: 1;
  panels: Partial<Record<WorkspacePanelId, PanelState>>;
  active: WorkspacePanelId;   // the focused dock panel
};

// The default dock layout: every panel docked, 'compose' active. Order follows the
// canonical studio order so flag-ON without saved state matches the fixed strip.
const DOCK_ORDER: WorkspacePanelId[] = [
  'compose', 'cowriter', 'assemble', 'planner', 'beats', 'graph', 'cast', 'relmap',
  'timeline', 'arc', 'worldmap', 'grounding', 'references', 'style', 'canon', 'critic',
  'threads', 'progress', 'quality', 'flywheel', 'settings',
];

export function defaultLayout(): WorkspaceLayout {
  const panels: Partial<Record<WorkspacePanelId, PanelState>> = {};
  DOCK_ORDER.forEach((id, i) => { panels[id] = { placement: 'dock', order: i }; });
  return { version: 1, panels, active: 'compose' };
}

// Validate a parsed layout (localStorage is untrusted — corruption → default). A
// layout is valid only if it is v1 with a panels object and a known active id.
export function isValidLayout(v: unknown): v is WorkspaceLayout {
  if (!v || typeof v !== 'object') return false;
  const l = v as Partial<WorkspaceLayout>;
  if (l.version !== 1 || !l.panels || typeof l.panels !== 'object') return false;
  if (typeof l.active !== 'string') return false;
  return true;
}
