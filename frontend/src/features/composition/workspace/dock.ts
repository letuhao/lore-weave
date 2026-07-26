// LOOM Composition (T5.4 M2/M3) — pure dock-layout helpers (tested in isolation).
import type { Rect, WorkspaceLayout, WorkspacePanelId } from './types';

// The 'threads' panel is conditional (the Work must opt into narrative_thread). The
// dock must NOT surface it when disabled, even though defaultLayout() seeds an entry
// for it (D-T5.4-THREADS-GATE). This predicate gates every dock listing.
function included(id: WorkspacePanelId, threadsEnabled: boolean): boolean {
  return id !== 'threads' || threadsEnabled;
}

function dockEntries(layout: WorkspaceLayout, threadsEnabled: boolean) {
  return (Object.entries(layout.panels) as [WorkspacePanelId, NonNullable<WorkspaceLayout['panels'][WorkspacePanelId]>][])
    .filter(([id, st]) => st.placement === 'dock' && included(id, threadsEnabled))
    // `?? 0` tolerates a hand-edited / partial persisted entry without a NaN sort.
    .sort((a, b) => (a[1].order ?? 0) - (b[1].order ?? 0));
}

/** The docked, NON-hidden panels in dock order — the tab strip. */
export function visibleDockIds(layout: WorkspaceLayout, threadsEnabled: boolean): WorkspacePanelId[] {
  return dockEntries(layout, threadsEnabled).filter(([, st]) => !st.hidden).map(([id]) => id);
}

/** The docked-but-hidden panels (the ComponentPicker re-show list). */
export function hiddenDockIds(layout: WorkspaceLayout, threadsEnabled: boolean): WorkspacePanelId[] {
  return dockEntries(layout, threadsEnabled).filter(([, st]) => st.hidden).map(([id]) => id);
}

/** arrayMove: move `activeId` to `overId`'s slot, returning the new id order (dnd-kit
 *  sortable semantics — same as Corkboard's same-band move). No-op ids → unchanged. */
export function computeReorder(ids: WorkspacePanelId[], activeId: string, overId: string): WorkspacePanelId[] {
  const from = ids.indexOf(activeId as WorkspacePanelId);
  const to = ids.indexOf(overId as WorkspacePanelId);
  if (from === -1 || to === -1 || from === to) return ids;
  const next = ids.slice();
  next.splice(to, 0, next.splice(from, 1)[0]);
  return next;
}

/** When hiding the active panel, pick the next visible panel to focus (so the
 *  content pane never goes blank). Returns null if nothing else is visible. */
export function nextActiveAfterHide(
  visible: WorkspacePanelId[], hidingId: WorkspacePanelId,
): WorkspacePanelId | null {
  const remaining = visible.filter((id) => id !== hidingId);
  if (!remaining.length) return null;
  const idx = visible.indexOf(hidingId);
  return remaining[Math.min(idx, remaining.length - 1)];
}

// ── M3: in-app floating windows ──────────────────────────────────────────────

/** The floated panels (each rendered as a FloatingWindow). Gated on threadsEnabled
 *  like the dock listings, sorted by dock `order` for a stable initial z-baseline. */
export function floatingDockIds(layout: WorkspaceLayout, threadsEnabled: boolean): WorkspacePanelId[] {
  return (Object.entries(layout.panels) as [WorkspacePanelId, NonNullable<WorkspaceLayout['panels'][WorkspacePanelId]>][])
    .filter(([id, st]) => st.placement === 'float' && included(id, threadsEnabled))
    .sort((a, b) => (a[1].order ?? 0) - (b[1].order ?? 0))
    .map(([id]) => id);
}

/** The popped-out panels (each driving a separate OS window via PopoutBridge). Gated
 *  on threadsEnabled like the other listings. These are NOT mounted in the opener's
 *  content area (they live in their own window) — only their bridge is. */
export function popoutDockIds(layout: WorkspaceLayout, threadsEnabled: boolean): WorkspacePanelId[] {
  return (Object.entries(layout.panels) as [WorkspacePanelId, NonNullable<WorkspaceLayout['panels'][WorkspacePanelId]>][])
    .filter(([id, st]) => st.placement === 'popout' && included(id, threadsEnabled))
    .sort((a, b) => (a[1].order ?? 0) - (b[1].order ?? 0))
    .map(([id]) => id);
}

/** A new floating window's initial geometry, cascaded by how many windows are already
 *  open so a freshly-floated panel doesn't land exactly on top of the last one. Clamped
 *  to a sane default size; the user then drags/resizes (persisted as rect). */
export function defaultFloatRect(openCount: number): Rect {
  const step = 28;
  const offset = (openCount % 6) * step;   // cascade, wrapping after 6 so it stays on-screen
  return { x: 96 + offset, y: 96 + offset, w: 520, h: 420 };
}
