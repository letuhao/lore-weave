import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { glossaryApi } from '../api';
import type { GlossaryEntitySummary } from '../types';

/** Tombstone tag: a rejected suggestion the writeback loop must not re-propose. */
const AI_REJECTED_TAG = 'ai-rejected';

/**
 * Controller for the "AI Suggestions" inbox (glossary AI-pipeline v2, mui #1).
 *
 * Lists the draft entities knowledge-service wrote back (tag `ai-suggested`)
 * and owns the two review actions:
 *   - promote → status='active' — the entity becomes canon; the existing
 *     glossary→KG sync then anchors it (glossary_entity_id), closing the
 *     discovery loop.
 *   - reject  → status='inactive' + `ai-rejected` tombstone — a future
 *     writeback batch skips this name (glossary extract-entities tombstone
 *     gate), so the user isn't re-asked about a suggestion they declined.
 *
 * Both actions invalidate the inbox query and the main entity list (the
 * entity moved out of the draft/ai-suggested set).
 */
export function useAiSuggestions(bookId: string) {
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['glossary-ai-suggestions', bookId],
    queryFn: () => glossaryApi.listAiSuggestions(bookId, accessToken!),
    enabled: !!accessToken,
  });

  const items: GlossaryEntitySummary[] = data?.items ?? [];
  const total = data?.total ?? 0;

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['glossary-ai-suggestions', bookId] });
    void queryClient.invalidateQueries({ queryKey: ['glossary-entities', bookId] });
  };

  const promote = async (entity: GlossaryEntitySummary) => {
    await glossaryApi.patchEntity(bookId, entity.entity_id, { status: 'active' }, accessToken!);
    invalidate();
  };

  const reject = async (entity: GlossaryEntitySummary) => {
    // tags is a full replacement on PATCH — keep ai-suggested (audit) and add
    // the tombstone. Idempotent if the tag is already present.
    const tags = entity.tags.includes(AI_REJECTED_TAG)
      ? entity.tags
      : [...entity.tags, AI_REJECTED_TAG];
    await glossaryApi.patchEntity(bookId, entity.entity_id, { status: 'inactive', tags }, accessToken!);
    invalidate();
  };

  return { items, total, isLoading, error, refetch, promote, reject };
}
