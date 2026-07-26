// Plan Hub v2 (spec 24 §H5 / PH20) — the WRITE half of the controller: the three drag-to-move
// mutations. Split out of usePlanHub (which owns the reads + collapse + selection) because the
// interaction rules below are the load-bearing part of H5 and deserve their own home + tests.
//
// The two-layer division of labour (the H5 law): the CANVAS resolves only the drop TARGET, by a pure
// hit-test on the layout; THIS hook decides whether that target means a real write, and what the
// write's arguments are — because only it holds parent_id / rank / version. A canvas that decided
// would have to re-derive server truth it doesn't have.
//
// Every move settles by RELOADING server truth (invalidate + reloadWindows): the server owns
// rank/story_order/depth (it renumbers, recomputes depth, bumps version), so the client must never
// become a second source of truth. The optimistic `patchWindow` is display-only — it re-places the
// card the instant the drag ends so it doesn't sit in its old slot for the round-trip, and the
// settle overwrites it either way (which also means a FAILED move rolls itself back for free).
//
// UNDO is one level, and its inverse is captured BEFORE the write from state we already hold — the
// server's answer no longer knows where the node came from. One level, not a stack: undoing an undo
// is just another move, and a deep stack would let a user walk back through writes that later work
// (or another collaborator) has already built on.
import { useCallback, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  assignChapters,
  createSceneLink,
  deleteSceneLink,
  getChildren,
  moveArc,
  reorderBookChapter,
  reorderNode,
} from '../api';
import { booksApi } from '@/features/books/api';
import type { ArcListNode, NodePosition, SceneLinkEdge, SummaryNode } from '../types';

const SIBLING_PAGE = 100;
const MAX_SIBLING_PAGES = 20; // a chapter with >2000 scenes is not a real book; bound the walk

/** book-service CLAMPS `limit` to 100 (server.go parseLimitOffset) — asking for more silently
 *  returns 100, so a whole-book listing MUST page by offset. */
const CHAPTER_PAGE = 100;
const MAX_CHAPTER_PAGES = 200; // 20k chapters

/**
 * The book's chapter ids in READING order, paged in FULL.
 *
 * Do not ask for `{limit: 500}` and trust it: book-service clamps to 100, so a >100-chapter book
 * came back truncated with no signal. Row-3's undo derives the moved chapter's PREVIOUS neighbour
 * from this sequence, so a chapter past #100 looked ABSENT — which collapsed to `previous = null`,
 * i.e. "it used to be the book's first chapter". Two consequences, both on the one gesture that
 * mutates the real manuscript: a drop at the head was swallowed as a no-op, and clicking Undo
 * MOVED THE CHAPTER TO POSITION 1. Page it in full, and let the caller fail loudly if the chapter
 * still isn't found rather than guess a position.
 */
async function bookChapterOrder(bookId: string, token: string): Promise<string[]> {
  const rows: { chapter_id: string; sort_order: number }[] = [];
  for (let page = 0; page < MAX_CHAPTER_PAGES; page++) {
    const res = await booksApi.listChapters(token, bookId, {
      limit: CHAPTER_PAGE,
      offset: page * CHAPTER_PAGE,
    });
    rows.push(...res.items);
    if (res.items.length < CHAPTER_PAGE) break;
  }
  return rows.sort((a, b) => a.sort_order - b.sort_order).map((c) => c.chapter_id);
}

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

/** A one-level undo of the last successful move. `run` re-issues the INVERSE write. */
export interface UndoableMove {
  label: string;
  run: () => void;
}

export interface PlanMoves {
  moveChapterToArc: (chapterId: string, arcId: string) => void;
  moveSceneToChapter: (sceneId: string, chapterId: string) => void;
  moveArcTo: (arcId: string, targetId: string) => void;
  /** H5 Row-3: place a chapter after `afterUnit` in the book's READING order (null ⇒ first). */
  reorderChapter: (chapterNodeId: string, afterUnit: NodePosition | null) => void;
  /** H5 Row-5 (PH20): DRAW a scene-link edge between two SCENE nodes. Rejects a stub endpoint (a
   *  chapter card / arc rollup standing in for something collapsed) with a reason. */
  linkScenes: (fromNodeId: string, toNodeId: string) => void;
  /** H5 Row-5 (PH20): DELETE a scene-link edge. Takes the whole EDGE, not just its id, so the undo
   *  can re-create it with its original kind + label. */
  unlinkScenes: (edge: SceneLinkEdge) => void;
  moving: boolean;
  moveError: string | null;
  /** The last successful move's inverse, or null. Cleared when a new move starts (one level). */
  undo: UndoableMove | null;
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
  /** Optimistically re-place a loaded row so the card lands where the user dropped it, instead of
   *  sitting in its old slot until the refetch returns. Display-only; `reloadWindows` overwrites it. */
  patchWindow: (nodeId: string, partial: Partial<SummaryNode>) => void;
}): PlanMoves {
  const { bookId, token, shellNodes, windowContent, reloadWindows, patchWindow } = input;
  const qc = useQueryClient();

  // ONE level of undo. Captured BEFORE each move from state we already hold, so the inverse is
  // exact — never reconstructed from the server's answer (which no longer knows where the node was).
  // A new move replaces it: undoing an undo is just another move, and a stack would let a user walk
  // back through writes other people may have built on.
  const [undo, setUndo] = useState<UndoableMove | null>(null);

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

  // The two inverses that need their own mutation (the others re-use the forward one with swapped
  // arguments). They deliberately re-read `windowContent` at RUN time: by then the settle has
  // reloaded, so the scene's `version` is the fresh one the OCC header needs.
  const undoSceneMutation = useMutation({
    mutationFn: (vars: { sceneId: string; chapterId: string; afterId: string | null }) => {
      const scene = windowContent[vars.sceneId];
      if (!scene) throw new Error('scene not loaded');
      return reorderNode(
        vars.sceneId,
        { new_parent_id: vars.chapterId, after_id: vars.afterId },
        scene.version,
        token!,
      );
    },
    onError: onFailed,
    onSettled: settle,
  });
  const undoArcMutation = useMutation({
    mutationFn: (vars: { arcId: string; parentId: string | null; afterId: string | null }) =>
      moveArc(vars.arcId, { new_parent_arc_id: vars.parentId, after_id: vars.afterId }, token!),
    onError: onFailed,
    onSettled: settle,
  });

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
      const from = windowContent[chapterId]?.structure_node_id ?? null;
      setMoveError(null);
      // Re-place the card NOW; reloadWindows will overwrite this with the server's answer either way.
      patchWindow(chapterId, { structure_node_id: arcId });
      chapterMutation.mutate({ chapterId, arcId }, {
        onSuccess: () => {
          // The inverse only exists if we knew where it came from. An unplanned chapter (no arc)
          // cannot be un-assigned by this route, so we offer no undo rather than a wrong one.
          setUndo(from ? { label: 'Chapter moved', run: () => moveChapterToArc(chapterId, from) } : null);
        },
      });
    },
    [token, windowContent, patchWindow, chapterMutation],
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
      const fromChapter = scene.parent_id;
      // Its predecessor in the OLD chapter — that chapter is necessarily EXPANDED (you just dragged
      // a scene out of it), so its siblings are loaded and the inverse position is exact.
      const oldSiblings = Object.values(windowContent)
        .filter((n) => n.kind === 'scene' && n.parent_id === fromChapter && n.id !== sceneId)
        .sort(byRank);
      const oldPrev = oldSiblings.filter((n) => byRank(n, scene) < 0).pop()?.id ?? null;

      setMoveError(null);
      patchWindow(sceneId, { parent_id: chapterId });
      sceneMutation.mutate({ sceneId, chapterId }, {
        onSuccess: () => {
          setUndo(
            fromChapter
              ? { label: 'Scene moved', run: () => undoSceneMutation.mutate({ sceneId, chapterId: fromChapter, afterId: oldPrev }) }
              : null,
          );
        },
      });
    },
    [token, windowContent, patchWindow, sceneMutation, undoSceneMutation],
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
      const self = shellNodes.find((n) => n.id === arcId);
      const oldParent = self?.parent_id ?? null;
      const oldPrev = self
        ? shellNodes
            .filter((n) => n.parent_id === oldParent && n.id !== arcId && byRank(n, self) < 0)
            .sort(byRank)
            .pop()?.id ?? null
        : null;

      setMoveError(null);
      arcMutation.mutate({ arcId, targetId }, {
        onSuccess: () => {
          setUndo({
            label: 'Arc moved',
            run: () => undoArcMutation.mutate({ arcId, parentId: oldParent, afterId: oldPrev }),
          });
        },
      });
    },
    [token, shellNodes, arcMutation, undoArcMutation],
  );

  // ── Row-3: drag a chapter along its lane → move it in the book's READING order. ──
  // This is the one gesture that mutates the MANUSCRIPT (book-service owns chapter order), so it is
  // the one where a mis-resolved target is genuinely destructive. Two guards live here:
  //   • the predecessor must be a CHAPTER we can NAME to the server (`after_chapter_id` is a book
  //     chapter_id). A collapsed arc's rollup hides chapters we haven't loaded, so "after that arc"
  //     is unnameable — we REFUSE with a message rather than quietly using the last loaded chapter,
  //     which would place this chapter BEFORE the collapsed arc's chapters (a move nobody asked for).
  //   • a drop that lands in the slot the chapter already occupies is a no-op (the server reorder is
  //     idempotent, so this is an optimization, never a correctness crutch).
  const reorderMutation = useMutation({
    mutationFn: async (vars: { chapterId: string; afterChapterId: string | null }) => {
      // Capture the chapter's CURRENT predecessor for the undo, from the book's own order. The
      // loaded windows are not enough: the chapter that precedes this one may belong to a collapsed
      // arc and never have been fetched, and an undo that guessed would silently move the chapter
      // somewhere it never was.
      const seq = await bookChapterOrder(bookId, token!);
      const i = seq.indexOf(vars.chapterId);
      // Not in the book's order at all (archived/purged under us, or a truncated read). NEVER fall
      // through to `previous = null` — that reads as "it was the first chapter" and would send the
      // undo to position 1.
      if (i < 0) throw new Error('That chapter is no longer in the book — the canvas reloaded.');
      const previous = i > 0 ? seq[i - 1] : null;

      // The no-op check lives HERE, not in the caller, because only the book's own order can decide
      // it. A caller comparing against the LOADED chapters would think a chapter whose predecessor
      // sits in a collapsed arc is already first, and swallow a real move — a silent failure, which
      // is far worse than the redundant (idempotent) write it was trying to avoid.
      if (previous === vars.afterChapterId) return { previous, skipped: true };

      await reorderBookChapter(
        bookId,
        { chapter_id: vars.chapterId, after_chapter_id: vars.afterChapterId },
        token!,
      );
      return { previous, skipped: false };
    },
    onError: onFailed,
    onSettled: settle,
  });
  const reorderChapter = useCallback(
    (chapterNodeId: string, afterUnit: NodePosition | null) => {
      if (!token) return;
      const moved = windowContent[chapterNodeId];
      if (!moved?.chapter_id) return; // not loaded / not a manuscript chapter ⇒ nothing to reorder

      if (afterUnit && afterUnit.shape !== 'chapter') {
        setMoveError('Expand that arc before moving a chapter past it.');
        return;
      }
      const afterNode = afterUnit ? windowContent[afterUnit.id] : null;
      if (afterUnit && !afterNode?.chapter_id) {
        setMoveError('Expand that arc before moving a chapter past it.');
        return;
      }

      setMoveError(null);
      const chapterId = moved.chapter_id;
      reorderMutation.mutate(
        { chapterId, afterChapterId: afterNode?.chapter_id ?? null },
        {
          onSuccess: (data) => {
            if (data.skipped) return; // it was already in that slot — nothing to undo
            setUndo({
              label: 'Chapter reordered',
              run: () => reorderMutation.mutate({ chapterId, afterChapterId: data.previous }),
            });
          },
        },
      );
    },
    [token, windowContent, reorderMutation],
  );

  // ── H5 Row-5 (PH20) — DRAW / DELETE a scene-link edge ──────────────────────────────────────
  //
  // The canvas reports only WHICH two handles were joined; the rules live here. Both endpoints must
  // be SCENE nodes: scene_link is the non-derivable scene→scene edge (F-H7), and a chapter-level
  // "link" is already expressible as reading order. Rejecting it here (with a reason) beats letting
  // the server 400 — the user gets told what the gesture means, not that it failed.
  const linkMutation = useMutation({
    mutationFn: (vars: { from: string; to: string; kind?: SceneLinkEdge['kind']; label?: string }) =>
      createSceneLink(
        bookId,
        { from_node_id: vars.from, to_node_id: vars.to, kind: vars.kind, label: vars.label },
        token!,
      ),
    onError: onFailed,
    onSettled: settle,
  });

  const unlinkMutation = useMutation({
    mutationFn: (linkId: string) => deleteSceneLink(linkId, token!),
    onError: onFailed,
    onSettled: settle,
  });

  const linkScenes = useCallback(
    (fromNodeId: string, toNodeId: string) => {
      if (!token) return;
      if (fromNodeId === toNodeId) return; // a self-loop; the table CHECK rejects it anyway
      const from = windowContent[fromNodeId];
      const to = windowContent[toNodeId];
      // A stub connector's endpoint is a CHAPTER card or an arc ROLLUP standing in for something
      // collapsed (PH13) — you cannot draw an edge to a placeholder, because we don't know which
      // scene inside it you meant. Say that, rather than creating a wrong edge or failing mutely.
      if (from?.kind !== 'scene' || to?.kind !== 'scene') {
        setMoveError('Scene links join two scenes — expand the chapters and drag scene to scene.');
        return;
      }
      setMoveError(null);
      linkMutation.mutate(
        { from: fromNodeId, to: toNodeId },
        {
          onSuccess: (link) => {
            setUndo({
              label: 'Scene link created',
              run: () => unlinkMutation.mutate(link.id),
            });
          },
        },
      );
    },
    [token, windowContent, linkMutation, unlinkMutation],
  );

  const unlinkScenes = useCallback(
    (edge: SceneLinkEdge) => {
      if (!token) return;
      setMoveError(null);
      // UNDOABLE. An earlier version took only the id and claimed no undo was possible ("the 204
      // carries no kind/label") — but the CLIENT already holds the whole edge, and createSceneLink
      // takes both. So a single click was irreversibly destroying a link for no reason, against this
      // codebase's own rule that reversibility is what licenses an un-confirmed write.
      unlinkMutation.mutate(edge.id, {
        onSuccess: () => {
          setUndo({
            label: 'Scene link deleted',
            run: () =>
              linkMutation.mutate({
                from: edge.from_node_id,
                to: edge.to_node_id,
                kind: edge.kind,
                label: edge.label ?? '',
              }),
          });
        },
      });
    },
    [token, unlinkMutation, linkMutation],
  );

  return {
    moveChapterToArc,
    moveSceneToChapter,
    moveArcTo,
    reorderChapter,
    linkScenes,
    unlinkScenes,
    moving:
      chapterMutation.isPending ||
      sceneMutation.isPending ||
      arcMutation.isPending ||
      reorderMutation.isPending ||
      undoSceneMutation.isPending ||
      undoArcMutation.isPending ||
      linkMutation.isPending ||
      unlinkMutation.isPending,
    moveError,
    undo,
  };
}
