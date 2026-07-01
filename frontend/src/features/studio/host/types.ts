// Studio Host (#07c) — the incremental registration + context layer, the VS Code extension-host
// analogue for the Writing Studio. Two stores:
//   • Registry — every dock tool panel registers on mount (unregisters on unmount) so the Command
//     Palette (#06b) and the agent rack (#07a) show ONLY mounted tools (incremental port).
//   • StudioContextBus — a pub/sub of read-only context slices (active chapter/scene/selection/
//     quality issue) so panels + chat exchange state without prop-drilling through dockview.

/** One dock tool's registration. `panelId` matches the dockview component id. */
export interface StudioToolRegistration {
  panelId: string;
  label: string;
  paletteCommand: string;   // "Studio: Open Cast" (#06b label — comes from here, never hardcoded)
  commandId: string;        // "studio.openPanel.cast"
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
  | { type: 'panels'; activePanelIds: string[] };

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
    default:
      return base;
  }
}
