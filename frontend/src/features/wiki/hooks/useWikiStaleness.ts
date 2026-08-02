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
  // The last sweep's KG coverage, held so the panel can keep SAYING the scan was
  // incomplete after the toast is gone. A toast is not a consumer — it is gone in four
  // seconds, and the state it warns about (a list that may be missing rows) persists.
  // `unchecked: null` = the server did not report coverage at all (a rollout skew against a
  // glossary build older than guardstatus). Still a warning, because "I cannot tell you how
  // much I compared" is not "I compared everything" — that equivalence is the entire bug.
  const [coverage, setCoverage] = useState<{ unchecked: number | null } | null>(null);

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
      // DoD-1 (Go) — the consumer for `kg_unchecked`. `found === 0` used to mean one thing
      // ("nothing drifted"); it now means two, and only this branch can tell them apart.
      //
      // Both fields, deliberately. On today's server `kg_status === 'degraded'` holds exactly
      // when `kg_unchecked > 0` (guardstatus.Over), and the mid-sweep `degradedSoFar` report —
      // the one that CAN be degraded with a zero count — never reaches the wire because its
      // caller 500s. That is a coupling between two files, not a guarantee: reading the status
      // too costs nothing and fails in the safe direction if the coupling ever breaks.
      //
      // The `typeof` is not defensive noise: the type says these are required and the WIRE
      // does not, so an older glossary would leave `kg_unchecked` undefined and `undefined > 0`
      // is false — the fail-open default wearing a required type. Absent ⇒ unknown ⇒ warn.
      const unchecked = typeof res.kg_unchecked === 'number' ? res.kg_unchecked : null;
      const degraded = unchecked === null || unchecked > 0 || res.kg_status === 'degraded';
      setCoverage(degraded ? { unchecked } : null);
      const message = degraded
        ? unchecked === null
          ? t('staleness.coverageUnknown')
          : t('staleness.rescanUnchecked', { count: unchecked })
        : res.recipe_swept
          ? t('staleness.rescanDone', { count: found })
          : t('staleness.rescanPartial', { count: found });
      // An incomplete answer is not a success, and `toast.success` is the green tick that
      // made the outage look like a clean book in the first place.
      (degraded ? toast.warning : toast.success)(message);
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
    /** Non-null only while the last sweep left articles uncompared. The panel renders it
     *  as a standing banner so an empty feed after a degraded scan cannot read as "clean". */
    coverage,
  };
}
