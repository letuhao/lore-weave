import { useState, useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { wikiApi } from '../api';
import type { WikiStalenessRow } from '../types';

/**
 * wiki-llm Phase-2b — the "Knowledge updates" change-feed controller (§5.3 DECIDE).
 *
 * Loads the pending staleness rows for a book (the capture/§5.2 consumer fills
 * them) and lets the user DISMISS one (accept-as-is, no spend). Regeneration is
 * driven separately via the M7b generate dialog (entity_ids batch) — when that
 * job completes it resolves the rows server-side, so this query is invalidated by
 * the same completion hook.
 */
export function useWikiStaleness(bookId: string) {
  const { accessToken } = useAuth();
  const { t } = useTranslation('wiki');
  const queryClient = useQueryClient();
  const [dismissing, setDismissing] = useState<string | null>(null);

  const query = useQuery<WikiStalenessRow[]>({
    queryKey: ['wiki-staleness', bookId],
    queryFn: async () => (await wikiApi.listStaleness(bookId, accessToken!)).items,
    enabled: !!accessToken,
  });

  const rows = query.data ?? [];

  const dismiss = useCallback(
    async (stalenessId: string) => {
      if (!accessToken) return;
      setDismissing(stalenessId);
      try {
        await wikiApi.dismissStaleness(bookId, stalenessId, accessToken);
        toast.success(t('staleness.dismissed'));
        queryClient.invalidateQueries({ queryKey: ['wiki-staleness', bookId] });
      } catch {
        toast.error(t('staleness.dismissFailed'));
      } finally {
        setDismissing(null);
      }
    },
    [accessToken, bookId, t, queryClient],
  );

  return { rows, count: rows.length, isLoading: query.isLoading, dismiss, dismissing };
}
