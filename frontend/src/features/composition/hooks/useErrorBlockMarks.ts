// Controller for the error-block highlights (atom-edit Phase D, D3d).
//
// Owns the fetch and pushes the rows at the editor HANDLE — the same imperative-setter pattern
// `setGlossaryEntities` / `setHeatmapTerms` already use, so the raw Editor never leaks out of
// TiptapEditor. The coordinate mapping lives with the live document, inside the handle.
import { useCallback, useEffect, useMemo, useState } from 'react';
import type { RefObject } from 'react';
import { useQuery } from '@tanstack/react-query';

import type { TiptapEditorHandle } from '@/components/editor/TiptapEditor';
import { errorBlocksApi, type ErrorBlock } from '../errorBlocks';

export interface ErrorBlockMarks {
  blocks: ErrorBlock[];
  openCount: number;
  /** Marks whose text could no longer be found in the document. Surfaced, never hidden: a
   *  highlight that quietly stops rendering is indistinguishable from a mark that was fixed. */
  driftedIds: string[];
  refresh: () => void;
}

export function useErrorBlockMarks(
  handleRef: RefObject<TiptapEditorHandle | null>,
  projectId: string | null,
  chapterId: string | null,
  token: string | null,
): ErrorBlockMarks {
  const [driftedIds, setDriftedIds] = useState<string[]>([]);

  const q = useQuery({
    queryKey: ['composition', 'error-blocks', projectId, chapterId],
    queryFn: () => errorBlocksApi.list(projectId!, chapterId!, token!),
    enabled: !!projectId && !!chapterId && !!token,
    staleTime: 30_000,
  });

  // Closed blocks are history — the author fixed or dismissed them and does not want their prose
  // still marked up. `orphaned` is excluded too: we cannot place it, so there is nothing to draw.
  const blocks = useMemo(
    () => (q.data?.blocks ?? []).filter((b) => b.status === 'open' || b.status === 'proposed'),
    [q.data],
  );

  // A synchronization effect, not event handling: the decoration set must follow whatever the
  // server currently says, and both the block list and the document change independently.
  useEffect(() => {
    const handle = handleRef.current;
    if (!handle) return;
    setDriftedIds(handle.setErrorBlocks(blocks));
  }, [handleRef, blocks]);

  const refresh = useCallback(() => { void q.refetch(); }, [q]);

  return { blocks, openCount: q.data?.open_count ?? 0, driftedIds, refresh };
}
