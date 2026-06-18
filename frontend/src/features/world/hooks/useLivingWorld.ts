// C28 (dị bản M6) — living-world data controller (FE MVC: this hook OWNS all
// fetch + the tree composition; the view renders only).
//
// Composes the world's timeline tree from EXISTING endpoints (no new BE):
//   1. `GET /v1/worlds/{id}/books` (C20) → the world's member books.
//   2. per book, `GET /v1/composition/books/{book_id}/work` (resolveWork) → every
//      Work on that book — canon AND its dị bản derivatives (COW keeps a
//      derivative on the source's book_id, so they surface together as the
//      resolution's `work` / `candidates`). Each Work carries C23's
//      `source_work_id` + `branch_point`.
//   3. `buildWorldTree` joins them into a trunk+branch tree via the
//      `source_work_id → id` chain — ONLY among this world's collected Works, so
//      no other world's branches bleed in.
//
// Branches are resolved client-side (the brief's "compose from existing
// endpoints" mandate) — there is no world-scoped Works read endpoint, and adding
// one would be BE work (scope-OUT). Read-only.
import { useMemo } from 'react';
import { useQuery, useQueries } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { compositionApi } from '@/features/composition/api';
import type { Work, WorkResolution } from '@/features/composition/types';
import { worldsApi } from '../api';
import {
  buildWorldTree,
  type WorldBookRef,
  type WorldTreeModel,
} from '../lib/livingWorldTree';

/** Collect every Work a resolution surfaced (the marked `work` plus any
 *  candidates — a book with a canon + N derivatives resolves to `candidates`
 *  holding all of them). De-duplication happens in buildWorldTree. */
export function worksFromResolution(res: WorkResolution | undefined): Work[] {
  if (!res) return [];
  const out: Work[] = [];
  if (res.work) out.push(res.work);
  if (res.candidates?.length) out.push(...res.candidates);
  return out;
}

export interface UseLivingWorldResult {
  tree: WorldTreeModel;
  isLoading: boolean;
  isError: boolean;
  error: Error | null;
  /** true once books resolved but no Works exist on any of them (nothing to
   *  show yet — the world has books but no composition Works). */
  isEmpty: boolean;
}

export function useLivingWorld(worldId: string | undefined): UseLivingWorldResult {
  const { accessToken } = useAuth();

  const booksQ = useQuery({
    queryKey: ['living-world', 'books', worldId],
    queryFn: () => worldsApi.listWorldBooks(accessToken!, worldId!, { limit: 200 }),
    enabled: !!accessToken && !!worldId,
  });

  const bookRefs: WorldBookRef[] = useMemo(
    () => (booksQ.data?.items ?? []).map((b) => ({ bookId: b.book_id, title: b.title })),
    [booksQ.data],
  );

  // Resolve every book's Works in parallel (one resolveWork call per book).
  const workQueries = useQueries({
    queries: bookRefs.map((b) => ({
      queryKey: ['living-world', 'works', b.bookId],
      queryFn: () => compositionApi.resolveWork(b.bookId, accessToken!),
      enabled: !!accessToken,
      staleTime: 30 * 1000,
    })),
  });

  // A CONTENT digest of every book's resolved Works — the spine fields the tree
  // is built from (id + source_work_id + branch_point). Keying the memo on this
  // (not on `q.data` object identity, which `.join` would stringify to a
  // count-only `[object Object]|…`) makes the tree recompute whenever a
  // resolution re-fetches with changed Works, not just on the first load.
  const worksDigest = useMemo(
    () =>
      workQueries
        .map((q) =>
          worksFromResolution(q.data)
            .map((w) => `${w.id ?? w.project_id}:${w.source_work_id ?? ''}:${w.branch_point ?? ''}`)
            .join(','),
        )
        .join('|'),
    [workQueries],
  );

  const worksByBook = useMemo(() => {
    const acc: Record<string, Work[]> = {};
    bookRefs.forEach((b, i) => {
      acc[b.bookId] = worksFromResolution(workQueries[i]?.data);
    });
    return acc;
    // Recompute on a real content change (worksDigest), not query-object identity.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bookRefs, worksDigest]);

  const tree = useMemo(() => buildWorldTree(bookRefs, worksByBook), [bookRefs, worksByBook]);

  const worksLoading = workQueries.some((q) => q.isLoading);
  const isLoading = booksQ.isLoading || (bookRefs.length > 0 && worksLoading);
  const firstError = (booksQ.error as Error | null) ?? (workQueries.find((q) => q.error)?.error as Error | null) ?? null;

  return {
    tree,
    isLoading,
    isError: booksQ.isError || workQueries.some((q) => q.isError),
    error: firstError,
    isEmpty: !isLoading && tree.nodes.length === 0,
  };
}
