// Plan Hub v2 (spec 24 §H5 / PH20) — the WRITE half of the controller: the three drag-to-move
// mutations. Split out of usePlanHub (which owns the reads + collapse + selection) because the
// interaction rules below are the load-bearing part of H5 and deserve their own home + tests.
//
// The two-layer division of labour (the H5 law): the CANVAS resolves only the drop TARGET, by a pure
// hit-test on the layout; THIS hook decides whether that target means a real write, and what the
// write's arguments are — because only it holds parent_id / rank / version. A canvas that decided
// would have to re-derive server truth it doesn't have.
//
// Every move settles by RELOADING server truth (invalidate + reloadWindows) rather than patching the
// cache optimistically: the server owns rank/story_order/depth (it renumbers, recomputes depth, and
// bumps version), so a client-side guess would drift. The brief re-place flicker is the accepted v1
// cost; optimistic re-place + undo are the deferred polish.
import { useCallback, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { assignChapters, getChildren, moveArc, reorderNode } from '../api';
import type { ArcListNode, SummaryNode } from '../types';

const SIBLING_PAGE = 100;
const MAX_SIBLING_PAGES = 20; // a chapter with >2000 scenes is not a real book; bound the walk

/** Byte-order rank compare (id tiebreak) — matches the server's `rank COLLATE "C", id` ordering. */
function byRank<T extends { rank: string; id: string }>(a: T, b: T): number {
  if (a.rank < b.rank) return -1;
  if (a.rank > b.rank) return 1;
  return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
}

/**
 * The id of the target chapter's LAST scene (null ⇒ it has none), asked of the SERVER.
 *
 * Do NOT infer this from the loaded window. `reorder` reads `after_id: null` as "make it the FIRST
 * child" and then dense-renumbers that chapter's scene story_order — so an empty window would
 * silently PREPEND the scene and shuffle the whole chapter. And the window is empty in exactly the
 * common case: you drop a scene onto some OTHER chapter's card, which is collapsed, so its scene
 * window was never fetched. One extra GET on a user-initiated drag is a fine price for a correct
 * append. The children route pages in (rank, id) order, so the last row of the last page IS the
 * last sibling.
 */
async function lastSceneOf(
  bookId: string,
  chapterId: string,
  excludeId: string,
  token: string,
): Promise<string | null> {
  let cursor: string | null = null;
  let last: SummaryNode | null = null;
  for (let page = 0; page < MAX_SIBLING_PAGES; page++) {
    const res = await getChildren(bookId, { parentId: chapterId }, { cursor, limit: SIBLING_PAGE, token });
    const scenes = res.items.filter((n) => n.kind === 'scene' && n.id !== excludeId).sort(byRank);
    if (scenes.length) last = scenes[scenes.length - 1];
    if (!res.next_cursor) break;
    cursor = res.next_cursor;
  }
  return last?.id ?? null;
}

export interface PlanMoves {
  moveChapterToArc: (chapterId: string, arcId: string) => void;
  moveSceneToChapter: (sceneId: string, chapterId: string) => void;
  moveArcTo: (arcId: string, targetId: string) => void;
  moving: boolean;
  moveError: string | null;
}

export function usePlanMoves(input: {
  bookId: string;
  token: string | null;
  /** The arc shell (read surface #1) — carries parent_id + rank, which the arc move needs. */
  shellNodes: ArcListNode[];
  /** The loaded chapter/scene rows — carry parent_id + version, which the scene move needs (OCC). */
  windowContent: Record<string, SummaryNode>;
  /** Refetch the loaded windows. REQUIRED: they are not react-query, so invalidateQueries misses
   *  them, and they are precisely the rows a move mutates (see usePlanWindows.reload). */
  reloadWindows: () => void;
}): PlanMoves {
  const { bookId, token, shellNodes, windowContent, reloadWindows } = input;
  const qc = useQueryClient();

  // ONE error slot for all three moves, cleared at the START of every move. Deriving it from the
  // three mutations' `error` fields instead would leave a stale banner up forever (react-query
  // clears a mutation's error only when that SAME mutation re-runs), and an old failure would
  // shadow a newer one under the `??` precedence.
  const [moveError, setMoveError] = useState<string | null>(null);

  const onFailed = useCallback((e: unknown) => {
    const err = e as Error & { status?: number };
    // 412 = the OCC conflict (scene reorder). The reload already fired in onSettled, so the message
    // says we re-synced — never "your edit was lost".
    if (err?.status === 412) {
      setMoveError('That node changed elsewhere — the canvas reloaded. Try the move again.');
      return;
    }
    setMoveError(err?.message || 'Move failed.');
  }, []);

  // Reload BOTH halves of server truth: the react-query reads (arc shell / overlay / links) and the
  // hand-rolled windows (the rows carrying the mutated structure_node_id / parent_id / version).
  const settle = useCallback(() => {
    void qc.invalidateQueries({ queryKey: ['plan-hub'] });
    reloadWindows();
  }, [qc, reloadWindows]);

  // ── Row-1: drag a chapter card into another lane → rebind its arc (structure_node_id). ──
  // The assign-chapters mirror is an idempotent, ADDITIVE bulk set (it updates only the passed ids;
  // it does not clear the arc's other members) and carries no OCC.
  const chapterMutation = useMutation({
    mutationFn: async (vars: { chapterId: string; arcId: string }) => {
      const res = await assignChapters(bookId, vars.arcId, [vars.chapterId], token!);
      // The route 200s even when it matched 0 rows (the arc or the chapter vanished / was archived
      // under us — the UPDATE's EXISTS + `kind='chapter' AND NOT is_archived` guards no-op'd). A 200
      // that moved nothing is a SILENT SUCCESS: surface it (`silent-success-is-a-bug`).
      if ((res.assigned ?? 0) < 1) {
        throw new Error('That chapter could not be moved — it may have been archived or removed.');
      }
      return res;
    },
    onError: onFailed,
    onSettled: settle,
  });
  const moveChapterToArc = useCallback(
    (chapterId: string, arcId: string) => {
      if (!token) return;
      setMoveError(null);
      chapterMutation.mutate({ chapterId, arcId });
    },
    [token, chapterMutation],
  );

  // ── Row-4: drag a scene card onto another chapter → re-parent it. A versioned node write, so it
  // carries OCC (If-Match: version → 412). We settle on SUCCESS **and** ERROR so a conflict reloads
  // the true state (the SceneRail "changed elsewhere — reloaded" recovery, never a silent overwrite).
  const sceneMutation = useMutation({
    mutationFn: async (vars: { sceneId: string; chapterId: string }) => {
      const scene = windowContent[vars.sceneId];
      if (!scene) throw new Error('scene not loaded');
      const afterId = await lastSceneOf(bookId, vars.chapterId, vars.sceneId, token!);
      return reorderNode(
        vars.sceneId,
        { new_parent_id: vars.chapterId, after_id: afterId },
        scene.version,
        token!,
      );
    },
    onError: onFailed,
    onSettled: settle,
  });
  const moveSceneToChapter = useCallback(
    (sceneId: string, chapterId: string) => {
      if (!token) return;
      const scene = windowContent[sceneId];
      // Unknown scene, or dropped back on its OWN chapter ⇒ no write (the canvas re-places the card).
      if (!scene || scene.parent_id === chapterId) return;
      setMoveError(null);
      sceneMutation.mutate({ sceneId, chapterId });
    },
    [token, windowContent, sceneMutation],
  );

  // ── Row-2: drag an ARC band onto another band → move it in the structure tree. The canvas reports
  // only WHICH band was hit; the nest-vs-sibling DECISION is here because it needs the shell's
  // parent_id/rank: a drop on a saga or a parent arc NESTS under it (append as its last child); a
  // drop on a LEAF arc makes the dragged arc that leaf's next SIBLING. Cycle / depth>2 /
  // parented-saga are the server's rules (clean 4xx → moveError); we only skip the two calls that
  // are guaranteed-pointless: dropping an arc on itself, or into its own subtree.
  const arcMutation = useMutation({
    mutationFn: (vars: { arcId: string; targetId: string }) => {
      const target = shellNodes.find((n) => n.id === vars.targetId);
      if (!target) throw new Error('target arc not loaded');
      // EXCLUDE the arc being moved from the target's children. If X is already T's last child,
      // including it would send after_id === X — and the server's sibling lookup excludes the moved
      // node (`id <> $3`), so after_id wouldn't resolve → a 400 whose message ("a saga cannot have a
      // parent, nesting is capped at depth 2…") explains the wrong thing entirely.
      const kids = shellNodes.filter((n) => n.parent_id === target.id && n.id !== vars.arcId);
      const nest = target.kind === 'saga' || kids.length > 0;
      const body = nest
        ? {
            new_parent_arc_id: target.id,
            after_id: kids.length ? [...kids].sort(byRank)[kids.length - 1].id : null,
          }
        : { new_parent_arc_id: target.parent_id, after_id: target.id };
      return moveArc(vars.arcId, body, token!);
    },
    onError: onFailed,
    onSettled: settle,
  });
  const moveArcTo = useCallback(
    (arcId: string, targetId: string) => {
      if (!token || arcId === targetId) return;
      // Dropping an arc into its OWN subtree is a cycle — the server rejects it; skip the round-trip.
      const parentOf = (id: string) => shellNodes.find((n) => n.id === id)?.parent_id ?? null;
      for (let p = parentOf(targetId), hops = 0; p && hops < 8; p = parentOf(p), hops++) {
        if (p === arcId) return;
      }
      setMoveError(null);
      arcMutation.mutate({ arcId, targetId });
    },
    [token, shellNodes, arcMutation],
  );

  return {
    moveChapterToArc,
    moveSceneToChapter,
    moveArcTo,
    moving: chapterMutation.isPending || sceneMutation.isPending || arcMutation.isPending,
    moveError,
  };
}
