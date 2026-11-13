// Chapter Browser (15_chapter_browser.md, task B3, decision CB8) — arc-grouping lookup for
// the browser's table view: "which arc is chapter N in" + a roman-numeral/label per arc group.
//
// #271 — this hook used to group by `kind === 'arc'` OUTLINE nodes, a shape pkg_lift_v1
// removed: arcs live in `structure_node`, outline nodes are chapter/scene only (#263), so
// the filter matched nothing and every grouping came back silently empty. It now reads the
// arc shells from the structure route the Plan Hub already uses (`GET /books/{id}/arcs`,
// BA11 — that route's own docstring names this table's group headers as a consumer) and
// binds chapters to arcs via `outline_node.structure_node_id` (23 BA2), which the
// root-level chapter page already carries. One arcs call + one cursor-followed chapter
// page replaces the old O(arcs) per-arc children fan-out.
//
// DOCK-2 (docs/standards/dockable-gui.md): reuses the SAME composition API calls
// `useManuscriptTree`/`ManuscriptNavigator` already use (`useWorkResolution`, `compositionApi.
// listOutlineChildren`) — it does NOT fork `useManuscriptTree`'s own lazy-expandable tree-
// building logic, because the shape needed here is different: a flat, fully-resolved
// chapter_id → arc_id map for table group-headers, not an incrementally-expanded tree.
//
// Fetch shape: the arcs call is one request (BA11); arc counts per book are small (tens,
// rarely low hundreds). Chapters are ROOT-level outline nodes (#263), so one cursor-followed
// root page covers the whole book regardless of arc count.
import { useEffect, useMemo, useRef, useState } from 'react';
import { useAuth } from '@/auth';
import { compositionApi } from '@/features/composition/api';
import type { OutlineNode } from '@/features/composition/types';
import type { ArcListNode } from '@/features/plan-hub/types';
import { getArcs } from '@/features/plan-hub/api';
import { useWorkResolution } from '@/features/composition/hooks/useWork';
import { useActiveWorkId } from '@/features/composition/hooks/useActiveWork';
import { resolveActiveWork } from '@/features/composition/workSelect';

// 1→I, 4→IV, … same converter `ManuscriptNavigator.tsx` uses for its arc badges (arcs never
// exceed a few dozen; the full converter is trivial + safe). Duplicated rather than imported:
// `ManuscriptNavigator.tsx` is a VIEW component (drags in react-i18next, lucide-react,
// @tanstack/react-virtual) and this is a "controller" hook — importing a view into a hook
// inverts this repo's MVC dependency direction (CLAUDE.md "Frontend Architecture Rules"), for a
// 10-line pure function that carries no domain logic to fork (DOCK-2 is about not forking the
// TREE-BUILDING logic, which this hook already avoids by reusing `listOutlineChildren` as-is).
function toRoman(n: number): string {
  if (n <= 0) return String(n);
  const table: Array<[number, string]> = [
    [1000, 'M'], [900, 'CM'], [500, 'D'], [400, 'CD'], [100, 'C'], [90, 'XC'],
    [50, 'L'], [40, 'XL'], [10, 'X'], [9, 'IX'], [5, 'V'], [4, 'IV'], [1, 'I'],
  ];
  let out = '';
  for (const [v, sym] of table) while (n >= v) { out += sym; n -= v; }
  return out;
}

// #318 P2 — BA11 returns list_tree order (depth, rank, id), NOT pre-order: ranks are
// allocated independently within each parent, so a second saga's arc (rank 'a') sorts
// before the first saga's second arc (rank 'b'), and every sub-arc sorts after every
// shallower arc. Numbering that flat list by index mislabels the groups
// (ChapterBrowserTitleView shows the numerals in its group headers). Walk the tree
// instead: children sorted by (rank, id), roots first, arcs collected in visit order.
// Sagas are interior nodes of the walk, never groups. Exported for unit tests.
export function arcsInSpecOrder(nodes: ArcListNode[]): ArcListNode[] {
  const byParent = new Map<string | null, ArcListNode[]>();
  for (const n of nodes) {
    const key = n.parent_id ?? null;
    const arr = byParent.get(key) ?? [];
    arr.push(n);
    byParent.set(key, arr);
  }
  // Rank is a fractional string; byte order matches the BE's COLLATE "C" sort.
  // Missing fields (older mocks / partial shells) sort as empty rank + root.
  const cmp = (a: ArcListNode, b: ArcListNode) => {
    const ra = a.rank ?? '';
    const rb = b.rank ?? '';
    if (ra !== rb) return ra < rb ? -1 : 1;
    return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
  };
  for (const arr of byParent.values()) arr.sort(cmp);
  const out: ArcListNode[] = [];
  const seen = new Set<string>(); // defensive: a duplicate/cyclic id never visits twice
  const walk = (parent: string | null) => {
    for (const n of byParent.get(parent) ?? []) {
      if (seen.has(n.id)) continue;
      seen.add(n.id);
      if (n.kind === 'arc') out.push(n);
      walk(n.id);
    }
  };
  walk(null);
  // Orphans (parent id absent from the list) would otherwise vanish — visit them as
  // roots, in rank order, after the connected tree.
  for (const n of nodes) {
    if (!seen.has(n.id)) walk(n.parent_id ?? null);
  }
  return out;
}

// Chapter-per-book counts can run large (a single book can hold hundreds of chapters), so the
// page size is generous; the loop still cursor-follows `next_cursor` rather than assuming a
// single page suffices.
const CHAPTERS_PAGE = 200;

/** Cursor-follow ALL root-level pages (chapters — outline nodes are chapter/scene only). */
async function fetchAllChapters(
  projectId: string, token: string, limit: number,
): Promise<OutlineNode[]> {
  const all: OutlineNode[] = [];
  let cursor: string | null = null;
  // eslint-disable-next-line no-constant-condition
  while (true) {
    const page = await compositionApi.listOutlineChildren(projectId, token, { parentId: null, cursor, limit });
    all.push(...page.items);
    if (!page.next_cursor) break;
    cursor = page.next_cursor;
  }
  return all;
}

export interface ChapterArcGroup {
  arcId: string;
  label: string; // e.g. "The Crimson Court"
  romanNumeral: string; // e.g. "II"
  chapterIds: Set<string>;
  chapterCount: number;
}

export interface UseChapterBrowserGroupsResult {
  hasWork: boolean;
  loading: boolean;
  groups: ChapterArcGroup[];
  arcIdForChapter: (chapterId: string) => string | undefined;
}

/**
 * Flat "which arc is chapter N in" lookup + per-arc chapter-id groups for the Chapter Browser's
 * table group-headers. Mirrors `useManuscriptTree`'s own Work-resolution fallback: a book with
 * no Composition Work returns `hasWork: false` immediately (no arcs to group by — same as the
 * Navigator's flat-chapter-list fallback).
 */
export function useChapterBrowserGroups(bookId: string): UseChapterBrowserGroupsResult {
  const { accessToken } = useAuth();
  const work = useWorkResolution(bookId, accessToken);
  const { data: activeWorkId } = useActiveWorkId(bookId, accessToken);

  // EC-3d: the ACTIVE Work's project (per-book pref, else canonical) — NOT candidates[0].
  const projectId = useMemo(
    () => resolveActiveWork(work.data, activeWorkId)?.project_id ?? null,
    [work.data, activeWorkId],
  );

  const [groups, setGroups] = useState<ChapterArcGroup[]>([]);
  const [arcMap, setArcMap] = useState<Map<string, string>>(new Map());
  const [fetching, setFetching] = useState(false);
  // Generation guard so a book-switch (or Work resolving away) never lets a stale in-flight
  // fetch overwrite the current book's groups (same discipline as useManuscriptTree's M1 fix).
  const genRef = useRef(0);

  useEffect(() => {
    if (work.isLoading) return;
    if (!projectId || !accessToken) {
      genRef.current += 1; // invalidate any in-flight fetch from a prior project
      setGroups([]);
      setArcMap(new Map());
      setFetching(false);
      return;
    }
    const gen = ++genRef.current;
    setFetching(true);
    (async () => {
      const [{ arcs }, chapters] = await Promise.all([
        getArcs(bookId, accessToken),
        fetchAllChapters(projectId, accessToken, CHAPTERS_PAGE),
      ]);

      // Arc shells in spec PRE-ORDER (parent/rank DFS over the BA11 shells — the flat
      // list_tree order is depth/rank/id, not pre-order; #318 P2). The browser groups
      // at ARC level only; sagas are interior nodes of the walk, not groups.
      const arcList = arcsInSpecOrder(arcs);
      const arcIds = new Set(arcList.map((a) => a.id));
      const chapterIdsByArc = new Map<string, Set<string>>();
      const nextArcMap = new Map<string, string>();
      for (const n of chapters) {
        // Root-level outline children are chapters (imported books can also carry stray
        // root scenes — no grouping meaning). Bind via structure_node_id (23 BA2);
        // unassigned chapters (PH21) and chapters bound to an unknown/archived arc
        // shell stay ungrouped, same posture as the Navigator's fallback.
        if (n.kind !== 'chapter' || !n.chapter_id) continue;
        const arcId = n.structure_node_id ?? null;
        if (!arcId || !arcIds.has(arcId)) continue;
        let set = chapterIdsByArc.get(arcId);
        if (!set) {
          set = new Set<string>();
          chapterIdsByArc.set(arcId, set);
        }
        set.add(n.chapter_id);
        nextArcMap.set(n.chapter_id, arcId);
      }
      const nextGroups: ChapterArcGroup[] = arcList.map((arc, i) => ({
        arcId: arc.id,
        label: arc.title || '(untitled)',
        romanNumeral: toRoman(i + 1),
        chapterIds: chapterIdsByArc.get(arc.id) ?? new Set<string>(),
        chapterCount: chapterIdsByArc.get(arc.id)?.size ?? 0,
      }));

      if (genRef.current !== gen) return; // stale — a later run already replaced this state
      setGroups(nextGroups);
      setArcMap(nextArcMap);
      setFetching(false);
    })().catch(() => {
      if (genRef.current === gen) {
        // A failed fetch degrades to "no groups" rather than throwing — the browser's Title
        // view falls back to an ungrouped table, same posture as the Navigator's own fallback.
        setGroups([]);
        setArcMap(new Map());
        setFetching(false);
      }
    });
  }, [projectId, accessToken, bookId, work.isLoading]);

  // O(1) lookup: a plain Map built once per completed fetch, not a linear scan per call.
  const arcIdForChapter = useMemo(() => {
    const map = arcMap;
    return (chapterId: string) => map.get(chapterId);
  }, [arcMap]);

  const hasWork = !work.isLoading && projectId != null;
  const loading = work.isLoading || (hasWork && fetching);

  return { hasWork, loading, groups, arcIdForChapter };
}
