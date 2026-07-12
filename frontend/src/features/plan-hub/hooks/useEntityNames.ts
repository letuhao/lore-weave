// 24 PH26 / read surface #6 — the book-wide entity-names map behind the cast chips.
//
// ONE cached load per book (the client follows the keyset cursor until exhausted — still one logical
// read, cached once). The load-bearing part is `complete`, which drives PH26's two ABSENCE cases:
//
//   map COMPLETE + id absent  → the entity genuinely doesn't exist  → a MISSING chip (a real problem,
//                                                                      deep-linked to the glossary)
//   map TRUNCATED + id absent → we just haven't read it yet         → a neutral unresolved chip
//
// Collapsing those two would make the Hub accuse the user's glossary of losing an entity it had
// merely not paged in — the `paged-join-against-complete-set-mislabels-not-yet-loaded-as-absent`
// bug class, which this repo has shipped before. Never a silent blank either way (PH26).
import { useCallback, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { glossaryApi } from '@/features/glossary/api';

export type EntityResolution =
  | { state: 'resolved'; name: string }
  /** The map is complete and this id is not in it — the reference is broken. */
  | { state: 'missing' }
  /** The map is incomplete, so we cannot say. Render neutrally; never accuse. */
  | { state: 'unknown' };

export interface EntityNamesMap {
  resolve: (entityId: string) => EntityResolution;
  /** Every id in the book resolved. False ⇒ absence proves nothing. */
  complete: boolean;
  loading: boolean;
}

export function useEntityNames(bookId: string): EntityNamesMap {
  const { accessToken } = useAuth();
  const token = accessToken ?? null;

  const { data, isLoading } = useQuery({
    // A book-scoped key distinct from the enrichment picker's, because this one carries `complete`.
    queryKey: ['plan-hub', 'entity-names', bookId],
    queryFn: () => glossaryApi.listEntityNamesWithMeta(bookId, token!),
    enabled: !!token && !!bookId,
    retry: false,
    // Names change rarely; the Hub reads them on every card. Cache hard.
    staleTime: 5 * 60_000,
  });

  const byId = useMemo(() => {
    const m = new Map<string, string>();
    for (const e of data?.items ?? []) m.set(e.entity_id, e.display_name);
    return m;
  }, [data]);

  // A FAILED / not-yet-loaded read is not a complete map. Defaulting `complete` to true here would
  // turn every cast id on the canvas into a "missing entity" warning the moment glossary hiccups.
  const complete = data?.complete ?? false;

  const resolve = useCallback(
    (entityId: string): EntityResolution => {
      const name = byId.get(entityId);
      if (name) return { state: 'resolved', name };
      return complete ? { state: 'missing' } : { state: 'unknown' };
    },
    [byId, complete],
  );

  return { resolve, complete, loading: isLoading };
}
