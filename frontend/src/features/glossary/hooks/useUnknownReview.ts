import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { glossaryApi } from '../api';
import { tieringApi } from '../tieringApi';
import type { UnknownEntity } from '../types';

/** What a single resolve did — drives the caller's toast. */
export type ResolveOutcome = { action: 'reassigned'; name: string };

/** How the author chose to resolve an unknown entity (collected by the modal).
 *
 *  `applyAll` is GONE (2026-07-28). It routed through `POST /kind-aliases`, which SS-4 Milestone C
 *  removed — probed live, it returns 405 — so the option every author saw pre-checked could only
 *  ever fail. Its promise ("a reusable alias so future extractions with this code resolve
 *  automatically") is the alias row itself, so a client-side bulk reassign would not deliver it
 *  either: it would fix today's entities and silently keep parking tomorrow's. The affordance
 *  comes back with the alias write in SS-7, retargeted at the tiered model. */
export type ResolveRequest =
  | { strategy: 'existing'; kindId: string }
  | { strategy: 'new'; code: string; name: string };

/**
 * Controller for the unknown-kind review GUI (kind-resolution epic E3).
 *
 * Surfaces the entities extract-entities couldn't resolve (parked under the
 * 'unknown' system kind, never dropped) and owns the triage orchestration via a
 * single `resolve(entity, request)`. Resolution maps to the glossary BE endpoints:
 *   - reassign-kind            : move just THIS entity onto a kind
 *   - books/{id}/ontology/kinds : mint a brand-new BOOK-tier kind, then reassign onto it
 *
 * The third route this used to call — `kind-aliases` (merge), which aliased source_code → kind
 * and moved every parked entity that arrived as that code — was removed by SS-4 Milestone C and
 * returns in SS-7 against the tiered model. Until then the bulk option is not offered, because
 * offering it meant a pre-checked box whose only outcome was a 405.
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
    // Mint the kind first when the author chose "new", so we have its id either way.
    //
    // The BOOK tier, not the old flat `POST /kinds` (which SS-4 removed — it 405s, which is what
    // broke this whole flow). There is no tier judgement to make here: `reassign-kind` validates
    // its target against `book_kinds WHERE book_kind_id = $1 AND book_id = $2`, so a kind minted
    // anywhere else would be rejected by the very next call.
    const kindId = req.strategy === 'new'
      ? (await tieringApi.createBookKind(bookId, { code: req.code, name: req.name }, accessToken!)).book_kind_id
      : req.kindId;

    await glossaryApi.reassignEntityKind(bookId, entity.entity_id, kindId, accessToken!);
    invalidate();
    return { action: 'reassigned', name: entity.name };
  };

  return { items, total, isLoading, error, refetch, resolve };
}
