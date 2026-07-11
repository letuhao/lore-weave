// Plan Hub v2 (spec 24, H2.4) — shared node presentation contracts + derived-scalar
// readers for the render-only canvas nodes. ONE home for the three-state treatment and
// the overlay/conformance lookups so ChapterNode/SceneNode/ArcRollupNode never each
// re-derive the same class map or key-lookup (css-var-duplicated-across-two-consumers-drifts).
//
// NB: the canvas payload is NodePosition (layout-only: id/shape/x/y/width/collapsed/
// storyOrder/rollupCount) — it carries NO title/status/tension. Titles + rich per-node
// scalars arrive with node enrichment in H4; here the label is the stable storyOrder
// placeholder and scalars are read ONLY from the overlay/conformance surfaces we already hold.
import type {
  ConformanceStatus,
  LaneBand,
  NodeContent,
  NodePosition,
  NodeUnionState,
  PlanOverlay,
  PlanOverlayRef,
} from '../types';

/** One book-wide lockfile pin chip (PH19). Sourced verbatim from the overlay so the chip
 *  contract has ONE home (a chip is stale — amber — when `live_version > pinned_version`). */
export type MotifChip = PlanOverlay['motif_chips'][number];

/** RF `data` payload for a content node (chapter/scene/arc-rollup). */
export interface PlanNodeData {
  node: NodePosition;
  /** Display scalars (title/status/…); undefined until the node's window loads ⇒ fall back to a
   *  story-order label. Arc-rollups get theirs from the shell (always present). */
  content?: NodeContent;
  overlay: PlanOverlay | null;
  conformance: ConformanceStatus | null;
  /** PH12 two-truths union state; undefined until the join resolves (renders neutral). */
  unionState?: NodeUnionState;
  selected: boolean;
  /** chapter ⇒ toggle scene branch; arc-rollup ⇒ expand the lane; scene ⇒ undefined. */
  onToggle?: () => void;
  /** H4.1 canon deep-link seam (PH18). When wired by the orchestrator, the canon badge becomes a
   *  button that opens the fired rule; when absent the badge degrades to a plain count chip (never a
   *  dead button — the `silent-success` bug class). See the TODO on `orderNodeBadges` for the wiring. */
  onOpenRef?: (ref: PlanOverlayRef) => void;
}

/** RF `data` payload for a background swimlane band. */
export interface LaneBandData {
  band: LaneBand;
  onToggleArc: (arcId: string) => void;
}

/**
 * Three-state card treatment (PH12): planned-only = dashed ghost, written = solid,
 * imported-unplanned = amber. `undefined` ⇒ neutral solid (union not yet resolved — we
 * never paint a state we don't have; absent ≠ a default state).
 */
export function unionStateClass(state?: NodeUnionState): string {
  switch (state) {
    case 'planned-only':
      return 'border-dashed border-muted-foreground/50 bg-transparent text-muted-foreground';
    case 'imported-unplanned':
      return 'border-amber-400 bg-amber-50 text-amber-900 dark:bg-amber-950/40 dark:text-amber-200';
    case 'written':
      return 'border-border bg-card';
    default:
      return 'border-border bg-card';
  }
}

/** The small union/status dot color (a stand-in for the status dot until H4 wires status). */
export function unionDotClass(state?: NodeUnionState): string {
  switch (state) {
    case 'planned-only':
      return 'bg-muted-foreground/40';
    case 'imported-unplanned':
      return 'bg-amber-500';
    case 'written':
      return 'bg-emerald-500';
    default:
      return 'bg-muted-foreground/40';
  }
}

/** Problem count for a node from the overlay (canon findings + open threads). null overlay ⇒ 0. */
export function problemCount(overlay: PlanOverlay | null, nodeId: string): number {
  const p = overlay?.problems.by_node[nodeId];
  return p ? p.canon + p.threads_open : 0;
}

/** Chapter tension from the overlay rollup. null overlay / no entry ⇒ null (render nothing). */
export function chapterTension(overlay: PlanOverlay | null, nodeId: string): number | null {
  const t = overlay?.tension_rollup.find((r) => r.chapter_node_id === nodeId);
  return t ? t.tension : null;
}

/**
 * Per-arc dirty flag from conformance (PH18). null conformance ⇒ NOT computed ⇒ false ⇒ no
 * badge (absent ≠ zero, absent ≠ clean — fe-status-default-fallback-signals-backend-field-omission).
 */
export function arcDirty(conformance: ConformanceStatus | null, structureId: string): boolean {
  if (!conformance) return false;
  return conformance.arcs.find((a) => a.structure_node_id === structureId)?.dirty ?? false;
}

/** Split of a node's problem counts (canon vs open-thread debt). null overlay / no entry ⇒ zeros.
 *  `problemCount` (above) stays the summed total for the rollup label; the badge row needs them apart
 *  so canon (deep-linkable) and threads read as distinct chips (PH18). */
export function problemBreakdown(
  overlay: PlanOverlay | null,
  nodeId: string,
): { canon: number; threads: number } {
  const p = overlay?.problems.by_node[nodeId];
  return { canon: p?.canon ?? 0, threads: p?.threads_open ?? 0 };
}

/** The first canon ref for a node (the fired rule the canon badge deep-links to). null ⇒ the count
 *  renders without a link target (the badge stays a plain chip). */
export function canonRef(overlay: PlanOverlay | null, nodeId: string): PlanOverlayRef | null {
  return overlay?.problems.by_node[nodeId]?.refs.find((r) => r.kind === 'canon') ?? null;
}

/** Lockfile chips hanging on this node (PH19). node_ref keys an outline_node.id (chapter/scene) OR a
 *  structure_node.id (arc lane) — one filter serves all three cards. null overlay ⇒ []. */
export function motifChipsFor(overlay: PlanOverlay | null, nodeId: string): MotifChip[] {
  return overlay?.motif_chips.filter((c) => c.node_ref === nodeId) ?? [];
}

/** PH23 chip caps — one home so every card truncates identically. Cast is reserved (see below). */
export const MOTIF_CHIP_CAP = 2;
export const CAST_CHIP_CAP = 3;

/**
 * An ordered decoration for the badge row. Discriminated by `kind` so each card renders the
 * treatment it wants (tension ⇒ sparkline, canon ⇒ deep-link chip, …) while the ORDER is decided
 * once here (PH23). `motif.stale` ⇒ the live registry version is newer than the pin (amber).
 */
export type NodeBadge =
  | { kind: 'canon'; count: number; ref: PlanOverlayRef | null }
  | { kind: 'dirty' }
  | { kind: 'threads'; count: number }
  | { kind: 'tension'; value: number }
  | { kind: 'motif'; chip: MotifChip; stale: boolean }
  | { kind: 'overflow'; count: number };

/**
 * THE single badge-precedence home (PH23). Produces the ordered, capped decoration list a card
 * renders left→right, so ChapterNode/SceneNode/ArcRollupNode never each re-decide order:
 *   canon  >  conformance-drift  >  thread-debt  >  pacing  >  motif chips (≤2)  >  +N overflow
 * `isArc` gates the drift badge (only structure nodes are in conformance.arcs); `showTension` gates
 * the pacing slot (per-chapter only — the overlay rollup is chapter-keyed, PH17). Absent data adds no
 * badge (absent ≠ zero — `fe-status-default-fallback-signals-backend-field-omission`).
 *
 * CAST (H4.4 / PH23's 3-cast cap): deliberately NOT emitted — `NodeContent` carries no
 * `present_entity_ids` (only SummaryNode does, server-capped to 3). Rendering a cast chip here would
 * be inventing data; it needs `present_entity_ids` threaded into `NodeContent` (a small contract add
 * for a later round) plus the PH26 entity-names map. `CAST_CHIP_CAP` is reserved for that.
 *
 * CANON DEEP-LINK (H4.1): the badge carries the fired rule's `ref`; the click is wired by the
 * orchestrator via `PlanNodeData.onOpenRef`. resolveStudioLink has no canon-rule URL route today
 * (no `/books/{id}/quality/canon` pattern, and a render-only node holds no host/bookId), so the seam
 * is a callback, not a URL — the orchestrator wires `onOpenRef` → `host.openPanel('quality-canon',
 * { ruleId: ref.id })` in PlanCanvas. Until wired, the chip renders the count (per H4.1's fallback).
 */
export function orderNodeBadges(input: {
  overlay: PlanOverlay | null;
  conformance?: ConformanceStatus | null;
  nodeId: string;
  isArc?: boolean;
  showTension?: boolean;
}): NodeBadge[] {
  const { overlay, conformance = null, nodeId, isArc = false, showTension = false } = input;
  const badges: NodeBadge[] = [];
  const { canon, threads } = problemBreakdown(overlay, nodeId);

  if (canon > 0) badges.push({ kind: 'canon', count: canon, ref: canonRef(overlay, nodeId) });
  if (isArc && arcDirty(conformance, nodeId)) badges.push({ kind: 'dirty' });
  if (threads > 0) badges.push({ kind: 'threads', count: threads });
  if (showTension) {
    const t = chapterTension(overlay, nodeId);
    if (t != null) badges.push({ kind: 'tension', value: t });
  }

  const motifs = motifChipsFor(overlay, nodeId);
  for (const chip of motifs.slice(0, MOTIF_CHIP_CAP)) {
    badges.push({ kind: 'motif', chip, stale: chip.live_version > chip.pinned_version });
  }
  if (motifs.length > MOTIF_CHIP_CAP) {
    badges.push({ kind: 'overflow', count: motifs.length - MOTIF_CHIP_CAP });
  }
  return badges;
}
