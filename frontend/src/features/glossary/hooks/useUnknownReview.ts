import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { glossaryApi } from '../api';
import type { UnknownEntity } from '../types';

/** What a single resolve did — drives the caller's toast. */
export type ResolveOutcome =
  | { action: 'merged'; count: number; code: string }
  | { action: 'reassigned'; name: string };

/** How the author chose to resolve an unknown entity (collected by the modal). */
export type ResolveRequest =
  | { strategy: 'existing'; kindId: string; applyAll: boolean }
  | { strategy: 'new'; code: string; name: string; applyAll: boolean };

/**
 * Controller for the unknown-kind review GUI (kind-resolution epic E3).
 *
 * Surfaces the entities extract-entities couldn't resolve (parked under the
 * 'unknown' system kind, never dropped) and owns the triage orchestration via a
 * single `resolve(entity, request)`. Resolution maps to the glossary BE endpoints:
 *   - reassign-kind        : move just THIS entity onto a kind
 *   - kind-aliases (merge) : alias source_code → kind AND move every parked entity
 *                            that arrived as that code (future extractions resolve too)
 *   - kinds (create)       : mint a brand-new kind, then reassign/merge onto it
 *
 * Every resolve invalidates the unknown queue + the entity list + the kinds list
 * (entity counts per kind and the alias table both shift on resolve).
 */
export function useUnknownReview(bookId: string) {
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['glossary-unknown', bookId],
    queryFn: () => glossaryApi.listUnknownEntities(bookId, accessToken!),
    enabled: !!accessToken,
  });

  const items: UnknownEntity[] = data?.items ?? [];
  const total = data?.total ?? 0;

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['glossary-unknown', bookId] });
    void queryClient.invalidateQueries({ queryKey: ['glossary-entities', bookId] });
    void queryClient.invalidateQueries({ queryKey: ['glossary-kinds'] });
  };

  const resolve = async (entity: UnknownEntity, req: ResolveRequest): Promise<ResolveOutcome> => {
    const code = entity.source_kind_code;
    const merge = req.applyAll && !!code;

    // Mint the kind first when the author chose "new", so we have its id either way.
    const kindId = req.strategy === 'new'
      ? (await glossaryApi.createKind(accessToken!, { code: req.code, name: req.name })).kind_id
      : req.kindId;

    let outcome: ResolveOutcome;
    if (merge) {
      // "Apply to all" always goes through the alias endpoint, which reassigns every
      // parked entity with this source code on the server (unbounded — not limited to
      // the loaded queue snapshot). When the new kind's code equals the source code,
      // the BE skips the redundant alias row but still performs the reassign.
      const res = await glossaryApi.createKindAlias(accessToken!, {
        alias_code: code!, kind_id: kindId, reassign: true, book_id: bookId,
      });
      outcome = { action: 'merged', count: res.reassigned, code: code! };
    } else {
      await glossaryApi.reassignEntityKind(bookId, entity.entity_id, kindId, accessToken!);
      outcome = { action: 'reassigned', name: entity.name };
    }

    invalidate();
    return outcome;
  };

  return { items, total, isLoading, error, refetch, resolve };
}
