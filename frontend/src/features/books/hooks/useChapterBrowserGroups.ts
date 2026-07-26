// Chapter Browser (15_chapter_browser.md, task B3, decision CB8) — arc-grouping lookup for
// the browser's table view: "which arc is chapter N in" + a roman-numeral/label per arc group.
//
// DOCK-2 (docs/standards/dockable-gui.md): reuses the SAME composition API calls
// `useManuscriptTree`/`ManuscriptNavigator` already use (`useWorkResolution`, `compositionApi.
// listOutlineChildren`) — it does NOT fork `useManuscriptTree`'s own lazy-expandable tree-
// building logic, because the shape needed here is different: a flat, fully-resolved
// chapter_id → arc_id map for table group-headers, not an incrementally-expanded tree.
//
// Fetch shape: arc counts per book are small (tens, rarely low hundreds) even for a
// 10k-chapter book, so a full (cursor-following) fetch of just the arc-level nodes is cheap.
// For EACH arc we then cursor-follow its direct chapter children to build that arc's
// chapterIds set. This is O(arcs) requests, not O(chapters) — the per-arc page size is large
// enough that a normal arc (tens to low hundreds of chapters) resolves in one request.
import { useEffect, useMemo, useRef, useState } from 'react';
import { useAuth } from '@/auth';
import { compositionApi } from '@/features/composition/api';
import type { OutlineNode } from '@/features/composition/types';
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

// Arc counts are small — one or a few pages covers virtually every book. Chapter-per-arc counts
// can run larger (a single arc can hold hundreds of chapters), so its page size is generous too;
// both loops still cursor-follow `next_cursor` rather than assuming a single page suffices.
const ARC_PAGE = 200;
const CHAPTERS_PER_ARC_PAGE = 200;

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

/** Cursor-follow ALL pages of one parent's direct children (arc-level or one arc's chapters). */
async function fetchAllChildren(
  projectId: string, token: string, parentId: string | null, limit: number,
): Promise<OutlineNode[]> {
  const all: OutlineNode[] = [];
  let cursor: string | null = null;
  // eslint-disable-next-line no-constant-condition
  while (true) {
    const page = await compositionApi.listOutlineChildren(projectId, token, { parentId, cursor, limit });
    all.push(...page.items);
    if (!page.next_cursor) break;
    cursor = page.next_cursor;
  }
  return all;
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
      const arcNodes = (await fetchAllChildren(projectId, accessToken, null, ARC_PAGE))
        .filter((n) => n.kind === 'arc');

      const nextGroups: ChapterArcGroup[] = [];
      const nextArcMap = new Map<string, string>();
      let ordinal = 0;
      for (const arc of arcNodes) {
        if (genRef.current !== gen) return; // a newer fetch superseded this one — abandon
        ordinal += 1;
        const children = await fetchAllChildren(projectId, accessToken, arc.id, CHAPTERS_PER_ARC_PAGE);
        const chapterIds = new Set<string>();
        for (const child of children) {
          // Only 'chapter' kind nodes matter for the browser's grouping; scenes/beats sit
          // below chapter level and carry no meaning for a "which arc is this chapter in" map.
          if (child.kind === 'chapter' && child.chapter_id) {
            chapterIds.add(child.chapter_id);
            nextArcMap.set(child.chapter_id, arc.id);
          }
        }
        nextGroups.push({
          arcId: arc.id,
          label: arc.title || '(untitled)',
          romanNumeral: toRoman(ordinal),
          chapterIds,
          chapterCount: chapterIds.size,
        });
      }

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
  }, [projectId, accessToken, work.isLoading]);

  // O(1) lookup: a plain Map built once per completed fetch, not a linear scan per call.
  const arcIdForChapter = useMemo(() => {
    const map = arcMap;
    return (chapterId: string) => map.get(chapterId);
  }, [arcMap]);

  const hasWork = !work.isLoading && projectId != null;
  const loading = work.isLoading || (hasWork && fetching);

  return { hasWork, loading, groups, arcIdForChapter };
}
