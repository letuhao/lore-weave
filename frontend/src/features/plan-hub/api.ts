// Plan Hub v2 (spec 24) — the API layer (React-MVC: no logic, just typed fetches).
// The seven read surfaces the canvas composes (24 §113). Every composition route is
// book-keyed + VIEW-gated server-side (BPS-8); the client passes the bearer token.
import { apiJson } from '../../api';
import type {
  ArcListNode,
  ChildrenPage,
  ConformanceStatus,
  PlanOverlay,
  SceneLinkEdge,
} from './types';

const COMP = '/v1/composition';

/** Read surface #1 — the whole structure shell (arcs/sagas) in one call. The composition route
 *  envelopes the shell as `{ nodes }` (the BA11 Chapter-Browser contract, shared route); each node
 *  carries the PH9/OQ-2 derived block (span/is_contiguous/chapter_count). We normalise to `{ arcs }`
 *  here so the Hub consumers read one name (a live smoke caught the `nodes`-vs-`arcs` drift). */
export async function getArcs(bookId: string, token: string): Promise<{ arcs: ArcListNode[] }> {
  const res = await apiJson<{ nodes?: ArcListNode[]; arcs?: ArcListNode[] }>(
    `${COMP}/books/${bookId}/arcs`,
    { token },
  );
  return { arcs: res.nodes ?? res.arcs ?? [] };
}

/** Read surface #2 — one keyset page of the children window. Exactly ONE axis:
 *  `structureNodeId` (chapters under an arc), `parentId` (scenes under a chapter), or
 *  `unassigned` (PH21 — chapters bound to no arc: the normal post-decompile state, which
 *  neither other axis can reach). The route 400s on zero or >1 axis (OQ-4 — there is no
 *  "omitted = whole book" anywhere). `detail=summary` is the canvas default. */
export function getChildren(
  bookId: string,
  axis: { structureNodeId: string } | { parentId: string } | { unassigned: true },
  opts: { cursor?: string | null; limit?: number; token: string },
): Promise<ChildrenPage> {
  const p = new URLSearchParams();
  if ('structureNodeId' in axis) p.set('structure_node_id', axis.structureNodeId);
  else if ('unassigned' in axis) p.set('unassigned', 'true');
  else p.set('parent_id', axis.parentId);
  if (opts.cursor) p.set('cursor', opts.cursor);
  if (opts.limit) p.set('limit', String(opts.limit));
  return apiJson<ChildrenPage>(
    `${COMP}/books/${bookId}/outline/children?${p.toString()}`,
    { token: opts.token },
  );
}

/** Read surface #4 — every scene-link edge of the book (sparse, one call). */
export function getSceneLinks(
  bookId: string,
  token: string,
): Promise<{ scene_links: SceneLinkEdge[] }> {
  return apiJson<{ scene_links: SceneLinkEdge[] }>(
    `${COMP}/books/${bookId}/scene-links`,
    { token },
  );
}

/** Read surface #3 — the decorations overlay (problems / tension / motif chips / tray). */
export function getPlanOverlay(bookId: string, token: string): Promise<PlanOverlay> {
  return apiJson<PlanOverlay>(`${COMP}/books/${bookId}/plan-overlay`, { token });
}

/** Read surface #7 — per-arc dirty badges + stale rollup (26 IX-14). Absent until 26
 *  ships ⇒ the caller renders NO badge (absent ≠ zero, OQ-8); a 404 here is that state. */
export function getConformanceStatus(
  bookId: string,
  token: string,
): Promise<ConformanceStatus> {
  return apiJson<ConformanceStatus>(
    `${COMP}/books/${bookId}/conformance/status`,
    { token },
  );
}

/** Result of the SC6 decompiler (`MaterializeResult.to_dict`). `work_resolved: false` with
 *  `scenes_total > 0` is the graceful no-Work guard — REPORTED, never a silent 200-with-zero. */
export interface MaterializeScenesResult {
  book_id: string;
  work_resolved: boolean;
  project_id: string | null;
  scenes_total: number;
  created: number;
  matched: number;
  skipped_authored: number;
  chapters: number;
  detail: string | null;
}

/** PH21 empty-state CTA #1 — "Extract the plan from the manuscript" (the DECOMPILER, 22 SC6).
 *  Upserts one spec node per parsed scene leaf (+ their chapter nodes), keyed on the book.
 *  DETERMINISTIC and $0 — no LLM — which is why it is a direct EDIT-gated call and not a
 *  propose→confirm priced endpoint (`materialize_scenes_v1`, the OQ-9 GUI mirror).
 *
 *  It extracts SCENES, not ARCS. Grouping chapters into arcs is the separate LLM step
 *  (`composition_arc_import_analyze`), which is a Tier-W MCP tool by design — agentic logic
 *  reachable only through the agent (MCP-first invariant), never a bespoke HTTP endpoint. So the
 *  freshly-minted chapters land UNASSIGNED (no arc lane) and the Hub says so. */
export function materializeScenes(
  bookId: string,
  token: string,
): Promise<MaterializeScenesResult> {
  return apiJson<MaterializeScenesResult>(
    `${COMP}/books/${bookId}/materialize-scenes`,
    { method: 'POST', token },
  );
}

/** H5 Row-5 write — DRAW a scene-link edge (PH20). Book-keyed: the Hub has no Work gate anywhere
 *  (PH9), so it never holds a `project_id` and cannot call the Work-keyed sibling. The server
 *  resolves the book's canonical Work itself and re-checks that BOTH endpoints are nodes of it — an
 *  EDIT grant on this book can never link a node from another. 409 SCENE_LINK_EXISTS on a duplicate
 *  (UNIQUE from,to,kind); 409 NO_CANONICAL_WORK when the book has no plan to link into. */
export function createSceneLink(
  bookId: string,
  body: { from_node_id: string; to_node_id: string; kind?: 'setup_payoff' | 'custom'; label?: string },
  token: string,
): Promise<SceneLinkEdge> {
  return apiJson<SceneLinkEdge>(`${COMP}/books/${bookId}/scene-links`, {
    method: 'POST',
    token,
    body: JSON.stringify(body),
  });
}

/** H5 Row-5 write — DELETE a scene-link edge (PH20). By-id: the server resolves the edge's scope
 *  from the row itself and gates EDIT on ITS book, so the gate and the mutation can never target
 *  different books. 204 on success; 404 (uniform, no existence oracle) if it isn't yours. */
export async function deleteSceneLink(linkId: string, token: string): Promise<void> {
  await apiJson<unknown>(`${COMP}/scene-links/${linkId}`, { method: 'DELETE', token });
}

/** H5 Row-2 write — move an ARC in the structure tree (the `composition_arc_move` mirror, PH20).
 *  Places `arcId` under `new_parent_arc_id` (null = a root) AFTER `after_id` (null = first). The
 *  server computes the fractional rank AND recomputes the moved subtree's `depth` in one txn; a
 *  cycle, a depth>2, a cross-book parent, or a parented saga come back as a clean 4xx conflict
 *  (never a 500), so the client need not re-implement those rules. No OCC — a structural move is
 *  guarded by the DB's constraints, not a row version. */
export function moveArc(
  arcId: string,
  body: { new_parent_arc_id: string | null; after_id: string | null },
  token: string,
): Promise<{ id: string; parent_id: string | null; depth: number }> {
  return apiJson<{ id: string; parent_id: string | null; depth: number }>(
    `${COMP}/arcs/${arcId}/move`,
    { method: 'POST', token, body: JSON.stringify(body) },
  );
}

/** H5 Row-4 write — re-parent / re-rank an outline node (the drag-reorder mirror, PH20). Places
 *  `nodeId` under `newParentId` directly AFTER `afterId` (null = first child); the server computes
 *  the fractional rank, inherits the new chapter's `chapter_id` for a re-parented scene, and
 *  renumbers scene `story_order` — all in ONE transaction. OCC is the existing `If-Match: <version>`
 *  header convention (PH20/F-H3): a stale version is a 412 NODE_VERSION_CONFLICT, which the caller
 *  recovers from by reloading (the SceneRail precedent) — never a silent overwrite. */
export function reorderNode(
  nodeId: string,
  body: { new_parent_id: string | null; after_id: string | null },
  version: number,
  token: string,
): Promise<{ id: string; parent_id: string | null; version: number }> {
  return apiJson<{ id: string; parent_id: string | null; version: number }>(
    `${COMP}/outline/nodes/${nodeId}/reorder`,
    { method: 'POST', token, headers: { 'If-Match': String(version) }, body: JSON.stringify(body) },
  );
}

/** H5 Row-3 write — move a chapter in the book's READING order (PH20). The only H5 gesture that
 *  crosses a service seam: the x-axis is the manuscript's order, which **book-service owns**. This
 *  composition route is the single entry point — it calls book-service's transactional renumber and
 *  then rebuilds composition's `story_order` mirror (incl. the canon-rule anchors that ride the same
 *  axis) so the client cannot leave the two halves inconsistent. Idempotent: re-issuing the same
 *  move converges, which is what makes the retry-on-502 (MIRROR_RESYNC_FAILED) safe.
 *  `after_chapter_id` is a BOOK chapter_id (not an outline node id); null ⇒ becomes chapter 1. */
export function reorderBookChapter(
  bookId: string,
  body: { chapter_id: string; after_chapter_id: string | null },
  token: string,
): Promise<{ book_id: string; resynced: Record<string, number> }> {
  return apiJson(`${COMP}/books/${bookId}/chapters/reorder`, {
    method: 'POST',
    token,
    body: JSON.stringify(body),
  });
}

/** H5 Row-1 write — attach chapter outline nodes to an arc (sets `structure_node_id`). The GUI
 *  mirror of `composition_arc_assign_chapters` (PH20); book-scoped both sides, EDIT-gated. Idempotent
 *  bulk set (no OCC/If-Match — not a versioned field write). Returns how many rows changed. */
export function assignChapters(
  bookId: string,
  structureNodeId: string,
  chapterNodeIds: string[],
  token: string,
): Promise<{ assigned: number; structure_node_id: string }> {
  return apiJson<{ assigned: number; structure_node_id: string }>(
    `${COMP}/books/${bookId}/arcs/assign-chapters`,
    {
      method: 'POST',
      token,
      body: JSON.stringify({ structure_node_id: structureNodeId, chapter_node_ids: chapterNodeIds }),
    },
  );
}
