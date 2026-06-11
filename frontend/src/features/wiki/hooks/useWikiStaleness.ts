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
  const [rescanning, setRescanning] = useState(false);

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

  // W2 — "Bỏ qua đã chọn": dismiss many rows in one call, then refresh the feed +
  // the sidebar badges (clearing is_knowledge_stale can change article rows).
  const dismissMany = useCallback(
    async (stalenessIds: string[]) => {
      if (!accessToken || stalenessIds.length === 0) return;
      try {
        const { dismissed } = await wikiApi.dismissStalenessBatch(bookId, stalenessIds, accessToken);
        toast.success(t('staleness.dismissedN', { count: dismissed }));
        queryClient.invalidateQueries({ queryKey: ['wiki-staleness', bookId] });
        queryClient.invalidateQueries({ queryKey: ['wiki-articles', bookId] });
      } catch {
        toast.error(t('staleness.dismissFailed'));
      }
    },
    [accessToken, bookId, t, queryClient],
  );

  // W2 — owner-triggered rescan: recipe-drift (versions from knowledge) + kg-drift.
  const rescan = useCallback(async () => {
    if (!accessToken) return;
    setRescanning(true);
    try {
      const res = await wikiApi.sweepStaleness(bookId, accessToken);
      const found = res.flagged + res.kg_flagged;
      toast.success(
        res.recipe_swept
          ? t('staleness.rescanDone', { count: found })
          : t('staleness.rescanPartial', { count: found }),
      );
      queryClient.invalidateQueries({ queryKey: ['wiki-staleness', bookId] });
      queryClient.invalidateQueries({ queryKey: ['wiki-articles', bookId] });
    } catch {
      toast.error(t('staleness.rescanFailed'));
    } finally {
      setRescanning(false);
    }
  }, [accessToken, bookId, t, queryClient]);

  return {
    rows,
    count: rows.length,
    isLoading: query.isLoading,
    dismiss,
    dismissing,
    dismissMany,
    rescan,
    rescanning,
  };
}
