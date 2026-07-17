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
  | { type: 'notificationsUnread'; count: number }
  // #19 — a one-shot "start the guided tour" request. WelcomePanel/UserGuidePanel are true
  // dockview panels (isolated from StudioFrameInner's tree, DOCK-4) with no direct access to the
  // tour/onboarding hooks that live at frame level, so they ask via the bus instead of a prop
  // callback (the same seam Quick Open/the agent's ui_focus_manuscript_unit already use to cross
  // that boundary). `tourId` is a plain string (not the `StudioTourId` union) — the host layer
  // stays domain-agnostic; the consumer (StudioFrame.tsx) validates it against STUDIO_TOURS.
  // Omitted `tourId` (the WelcomePanel's quick-start button) falls back to the account's role tour.
  | { type: 'startGuidedTour'; tourId?: string }
  // 24 PH25 — the Plan navigator rail lives in the ACTIVITY BAR, outside the dock, so it cannot
  // hand the Plan Hub a callback. Its click contract is fixed: "row click focuses the node on the
  // Hub canvas (opening plan-hub if closed) — NEVER the Editor". It therefore asks via the bus,
  // exactly like the guided-tour request above (a one-shot request + a seq, so focusing the SAME
  // node twice still pans).
  | { type: 'planFocusNode'; nodeId: string }
  // 32 AI-1 — the arc-inspector's subject. plan-hub publishes it on an arc/saga node selection;
  // the inspector subscribes. The ONLY studio-internal transport the agent needs to drive the
  // panel (a bare-id `ui_open_studio_panel` open lands here; the panel's picker is the fallback).
  | { type: 'arc'; arcId: string }
  // S7 D-CAST-ARC-BUS-SLICE — the cast codex's selected character. CastPanel publishes it when a
  // row's "view arc" is clicked; an ALREADY-OPEN character-arc panel subscribes so clicking a
  // different cast row switches the arc's subject (tier-2 live update). Mirrors 'arc'/'scene':
  // params (tier-1 deep-link) still win, the in-panel picker (tier-3) remains the fallback.
  | { type: 'castEntity'; entityId: string };

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
  /** Bumped by 'startGuidedTour' — consumers (StudioFrameInner) diff it against the last value
   *  they've seen to fire the tour exactly once per request, never on initial mount. */
  guidedTourRequestSeq?: number;
  /** The tourId of the most recent 'startGuidedTour' request, or undefined for "use the
   *  account's role tour" (the WelcomePanel's quick-start button never sets this). */
  guidedTourRequestedId?: string;
  /** 24 PH25 — the node the Plan rail last asked the Hub to focus, and a seq the Hub diffs so a
   *  repeat request on the SAME node still pans (and a mount never fires a stale one). */
  planFocusNodeId?: string;
  planFocusSeq?: number;
  /** 32 AI-1 — the arc/saga the inspector is showing (an outline `structure_node` id). */
  activeArcId?: string;
  /** S7 D-CAST-ARC-BUS-SLICE — the cast character last selected for its arc (a KG entity id).
   *  The character-arc panel reads it as tier-2 (params ?? this ?? picker) so an open panel
   *  re-subjects when a different cast row is clicked. */
  activeCastEntityId?: string;
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
    case 'startGuidedTour':
      return { ...base, guidedTourRequestSeq: (s.guidedTourRequestSeq ?? 0) + 1, guidedTourRequestedId: e.tourId };
    case 'planFocusNode':
      return { ...base, planFocusNodeId: e.nodeId, planFocusSeq: (s.planFocusSeq ?? 0) + 1 };
    case 'arc':
      return { ...base, activeArcId: e.arcId };
    case 'castEntity':
      return { ...base, activeCastEntityId: e.entityId };
    default:
      return base;
  }
}
