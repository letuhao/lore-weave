// Studio Host (#07c) — the incremental registration + context layer, the VS Code extension-host
// analogue for the Writing Studio. Two stores:
//   • Registry — every dock tool panel registers on mount (unregisters on unmount) so the Command
//     Palette (#06b) and the agent rack (#07a) show ONLY mounted tools (incremental port).
//   • StudioContextBus — a pub/sub of read-only context slices (active chapter/scene/selection/
//     quality issue) so panels + chat exchange state without prop-drilling through dockview.

/** A status-bar contribution (#11 F2 — VS Code StatusBarItem analogue). Items render INSIDE
 * `StudioStatusBar` between its fixed chrome; each `component` is fully self-contained (owns its
 * data hooks + click handlers) so a badge stays live while its panel is closed. Registered at
 * StudioFrame level (StudioStatusContributions), NOT inside panels. */
export interface StudioStatusBarItem {
  id: string;
  side: 'left' | 'right';
  /** Lower = closer to the edge of its side. Ties keep registration order. */
  order?: number;
  component: import('react').FunctionComponent;
}

/** One dock tool's registration. `panelId` matches the dockview component id. */
export interface StudioToolRegistration {
  panelId: string;
  label: string;
  paletteCommand: string;   // "Studio: Open Cast" (#06b label — comes from here, never hardcoded)
  commandId: string;        // "studio.openPanel.cast"
  description?: string;      // #06b muted subtitle ("Cast & relationships")
  mcpToolPrefixes?: string[];
  mcpTools?: string[];
  frontendTools?: string[];
  skills?: string[];
  contributeContext?: () => StudioContextSlice | null;
}

/** A panel's contributed context slice (extensible — new keys additive only). */
export interface StudioContextSlice {
  activeChapterId?: string;
  activeSceneId?: string;
  selectionRange?: { from: number; to: number };
  qualityIssueRef?: { promiseId: string; chapterId?: string };
}

/** Events panels publish to the bus. */
export type StudioBusEvent =
  | { type: 'chapter'; chapterId: string; bookId: string }
  | { type: 'scene'; sceneId: string; chapterId: string }
  | { type: 'selection'; range: { from: number; to: number }; chapterId: string }
  | { type: 'qualityIssue'; promiseId: string; chapterId?: string }
  | { type: 'panels'; activePanelIds: string[] }
  // #11 F2 — the authoritative unread count. Published by the status item (seed + SSE bump) AND
  // by the notifications panel after mark-read, so badge ↔ panel never drift (the same MED-1
  // class NotificationBell fixed with a route-change resync — no routes here, so it's bus-owned).
  | { type: 'notificationsUnread'; count: number };

/** The bus's current merged snapshot. `revision` increments on every publish (so a chat turn can
 * stamp `context_revision`). */
export interface StudioBusSnapshot {
  revision: number;
  bookId: string;
  activeChapterId?: string;
  activeSceneId?: string;
  selectionRange?: { from: number; to: number };
  qualityIssueRef?: { promiseId: string; chapterId?: string };
  activePanelIds: string[];
  notificationsUnread?: number;
}

/** Reduce a bus event onto the snapshot (pure — one new object, revision bumped). */
export function applyBusEvent(s: StudioBusSnapshot, e: StudioBusEvent): StudioBusSnapshot {
  const base = { ...s, revision: s.revision + 1 };
  switch (e.type) {
    case 'chapter':
      return { ...base, activeChapterId: e.chapterId, activeSceneId: undefined };
    case 'scene':
      return { ...base, activeSceneId: e.sceneId, activeChapterId: e.chapterId };
    case 'selection':
      return { ...base, selectionRange: e.range, activeChapterId: e.chapterId };
    case 'qualityIssue':
      return { ...base, qualityIssueRef: { promiseId: e.promiseId, chapterId: e.chapterId } };
    case 'panels':
      return { ...base, activePanelIds: e.activePanelIds };
    case 'notificationsUnread':
      return { ...base, notificationsUnread: Math.max(0, e.count) };
    default:
      return base;
  }
}
