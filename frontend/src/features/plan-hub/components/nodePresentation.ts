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
} from '../types';

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
