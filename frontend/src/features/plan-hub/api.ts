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

/** Read surface #2 — one keyset page of the children window. Exactly one axis:
 *  `structureNodeId` (chapters under an arc) OR `parentId` (scenes under a chapter).
 *  The route 400s on neither/both (OQ-4). `detail=summary` is the canvas default. */
export function getChildren(
  bookId: string,
  axis: { structureNodeId: string } | { parentId: string },
  opts: { cursor?: string | null; limit?: number; token: string },
): Promise<ChildrenPage> {
  const p = new URLSearchParams();
  if ('structureNodeId' in axis) p.set('structure_node_id', axis.structureNodeId);
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
