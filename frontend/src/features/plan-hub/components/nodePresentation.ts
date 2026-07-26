// Plan Hub v2 (spec 24, H2.4) — shared node presentation contracts + derived-scalar
// readers for the render-only canvas nodes. ONE home for the three-state treatment and
// the overlay/conformance lookups so ChapterNode/SceneNode/ArcRollupNode never each
// re-derive the same class map or key-lookup (css-var-duplicated-across-two-consumers-drifts).
//
// NB: the canvas payload is NodePosition (layout-only: id/shape/x/y/width/collapsed/
// storyOrder/rollupCount) — it carries NO title/status/tension. Titles + rich per-node
// scalars arrive with node enrichment in H4; here the label is the stable storyOrder
// placeholder and scalars are read ONLY from the overlay/conformance surfaces we already hold.
import type { EntityResolution } from '../hooks/useEntityNames';
import type {
  ArcPagination,
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
  /** H2.6 "you are here": this node's chapter is the one open in the editor (bus active-chapter).
   *  A distinct highlight from `selected` — the two can be true at once. */
  isHere?: boolean;
  /** chapter ⇒ toggle scene branch; arc-rollup ⇒ expand the lane; scene ⇒ undefined. */
  onToggle?: () => void;
  /** H4.1 canon deep-link seam (PH18). When wired by the orchestrator, the canon badge becomes a
   *  button that opens the fired rule; when absent the badge degrades to a plain count chip (never a
   *  dead button — the `silent-success` bug class). See the TODO on `orderNodeBadges` for the wiring. */
  onOpenRef?: (ref: PlanOverlayRef, nodeId: string) => void;
  /** PH13 — scene-links folded INSIDE this card (both endpoints collapsed into it, or its partner is
   *  off-screen). Badged so a collapsed card accounts for the edges it swallowed rather than letting
   *  them vanish. 0 ⇒ no badge. */
  hiddenEdges?: number;
  /** PH26 — resolve a cast entity id to a name / missing / unknown. Absent ⇒ no cast chips. */
  resolveEntity?: (entityId: string) => EntityResolution;
  /** PH15 — this node matches the toolbar's find query. undefined ⇒ no query is active. */
  matched?: boolean;
}

/** RF `data` payload for a background swimlane band. */
export interface LaneBandData {
  band: LaneBand;
  onToggleArc: (arcId: string) => void;
  /** H5 Row-2: this band can be dragged (by its header) to move the arc. Sagas never drag. */
  draggable?: boolean;
  /** Absent ⇒ the lane is collapsed / has nothing paged (no counter, no button). */
  pagination?: ArcPagination;
  onLoadMore?: (arcId: string) => void;
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

/** Every overlay ref of one kind on a node (PH16's "Canon here" / thread-debt drawer facets). The
 *  refs are ALREADY in memory from the cold-open overlay — the drawer's canon facet used to say
 *  "loads in H4" long after H4 had shipped, which read as a missing feature rather than a stale
 *  comment. Counts stay exact even when the payload's refs were capped (OUT-5); the caller surfaces
 *  `problems.refs_capped` so a count of 3 over a list of 1 is explained, not mysterious. */
export function refsFor(
  overlay: PlanOverlay | null,
  nodeId: string,
  kind: 'canon' | 'thread',
): PlanOverlayRef[] {
  return (overlay?.problems.by_node[nodeId]?.refs ?? []).filter((r) => r.kind === kind);
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
  /** PH26 — one cast member. `resolution` distinguishes a name we HAVE, a reference that is genuinely
   *  BROKEN (the map is complete and the id isn't in it), and one we simply haven't paged in. */
  | { kind: 'cast'; entityId: string; resolution: EntityResolution }
  | { kind: 'motif'; chip: MotifChip; stale: boolean }
  /** `of` discriminates the two overflow sources — cast AND motif can both overflow on one card, and
   *  without it they collide on the React key and the tooltip lies about which is truncated. */
  | { kind: 'overflow'; count: number; of: 'cast' | 'motif' };

/**
 * THE single badge-precedence home (PH23). Produces the ordered, capped decoration list a card
 * renders left→right, so ChapterNode/SceneNode/ArcRollupNode never each re-decide order:
 *   canon  >  conformance-drift  >  thread-debt  >  pacing  >  motif chips (≤2)  >  +N overflow
 * `isArc` gates the drift badge (only structure nodes are in conformance.arcs); `showTension` gates
 * the pacing slot (per-chapter only — the overlay rollup is chapter-keyed, PH17). Absent data adds no
 * badge (absent ≠ zero — `fe-status-default-fallback-signals-backend-field-omission`).
 *
 * CAST (H4.4 / PH23's 3-cast cap): emitted from `content.castIds` — server-capped to 3, which is
 * exactly what a card may render — with `content.castCount` driving the `+N`. The ids had been on the
 * wire since H1.1; the NodeContent map dropped them, so the chips had no data source at all. Names
 * resolve through the PH26 entity-names map (`resolveEntity`); an UNRESOLVED id renders as a missing
 * warning ONLY when that map is complete (absent ≠ missing).
 *
 * CANON DEEP-LINK (H4.1/PH18): the badge carries the fired rule's `ref`, and NodeBadges renders it
 * as a button when `onOpenRef` is present. The seam is a CALLBACK, not a URL — resolveStudioLink has
 * no canon-rule route, and a render-only node holds no host/bookId. It is wired by PlanHubPanel
 * (the orchestrator, which owns the host) → PlanCanvas → node `data` → NodeBadges.
 *
 * That last hop is the one that was missing: every node card read `data.onOpenRef` and every badge
 * honoured it, but PlanCanvas never PUT it in `data`, so the whole chain resolved to `undefined` and
 * the canon badge was permanently a plain chip. A comment here even claimed the canvas wired it. The
 * lesson: a seam that only ever gets `undefined` is indistinguishable from a designed fallback.
 */
export function orderNodeBadges(input: {
  overlay: PlanOverlay | null;
  conformance?: ConformanceStatus | null;
  nodeId: string;
  isArc?: boolean;
  showTension?: boolean;
  /** PH26 — the node's cast + the resolver. Omitted ⇒ no cast chips (a read-only/rail context). */
  content?: NodeContent;
  resolveEntity?: (entityId: string) => EntityResolution;
}): NodeBadge[] {
  const {
    overlay, conformance = null, nodeId, isArc = false, showTension = false,
    content, resolveEntity,
  } = input;
  const badges: NodeBadge[] = [];
  const { canon, threads } = problemBreakdown(overlay, nodeId);

  if (canon > 0) badges.push({ kind: 'canon', count: canon, ref: canonRef(overlay, nodeId) });
  if (isArc && arcDirty(conformance, nodeId)) badges.push({ kind: 'dirty' });
  if (threads > 0) badges.push({ kind: 'threads', count: threads });
  if (showTension) {
    const t = chapterTension(overlay, nodeId);
    if (t != null) badges.push({ kind: 'tension', value: t });
  }

  // PH23 cast chips (≤3 — the server already capped the ids to exactly that). We render a chip only
  // when we can resolve it OR when we can honestly say the reference is broken; with no resolver we
  // render nothing rather than a row of raw UUIDs.
  if (content && resolveEntity) {
    for (const id of content.castIds.slice(0, CAST_CHIP_CAP)) {
      badges.push({ kind: 'cast', entityId: id, resolution: resolveEntity(id) });
    }
    // The +N is driven by the EXACT roster size, not the capped list — a 9-person scene must read
    // "+6", not "+0" (the count is exact on the wire precisely so this can be true).
    const extra = content.castCount - Math.min(content.castIds.length, CAST_CHIP_CAP);
    if (extra > 0) badges.push({ kind: 'overflow', count: extra, of: 'cast' });
  }

  const motifs = motifChipsFor(overlay, nodeId);
  for (const chip of motifs.slice(0, MOTIF_CHIP_CAP)) {
    badges.push({ kind: 'motif', chip, stale: chip.live_version > chip.pinned_version });
  }
  if (motifs.length > MOTIF_CHIP_CAP) {
    badges.push({ kind: 'overflow', count: motifs.length - MOTIF_CHIP_CAP, of: 'motif' });
  }
  return badges;
}
