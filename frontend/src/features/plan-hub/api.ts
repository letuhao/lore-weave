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

/** Read surface #1 — the whole structure shell (arcs/sagas) in one call. */
export function getArcs(bookId: string, token: string): Promise<{ arcs: ArcListNode[] }> {
  return apiJson<{ arcs: ArcListNode[] }>(`${COMP}/books/${bookId}/arcs`, { token });
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
