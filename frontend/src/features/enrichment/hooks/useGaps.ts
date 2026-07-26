import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { enrichmentApi } from '../api';
import type { Gap, EnrichTarget } from '../types';

/** Detect under-described entities (read-only) + enqueue auto-enrich (background
 *  job). Detect is on-demand (a button), so it owns its own state rather than a
 *  query. Auto-enrich refreshes the jobs + proposals lists. */
export function useGaps(bookId: string) {
  const { accessToken } = useAuth();
  const qc = useQueryClient();
  const { t } = useTranslation('enrichment');
  const [gaps, setGaps] = useState<Gap[] | null>(null);
  const [needsExtraction, setNeedsExtraction] = useState(false);
  const [detecting, setDetecting] = useState(false);
  const [enriching, setEnriching] = useState(false);

  const detect = async () => {
    setDetecting(true);
    try {
      const r = await enrichmentApi.detectGaps(bookId, accessToken!);
      setGaps(r.gaps);
      // C2 "extract first" signal — an unextracted book has 0 entities → 0 gaps,
      // which is NOT "all well-described" but "nothing to enrich yet" (KB2).
      setNeedsExtraction(!!r.needs_extraction);
      return r;
    } catch (e) {
      toast.error((e as Error).message);
      return null;
    } finally {
      setDetecting(false);
    }
  };

  const autoEnrich = async (body: {
    embedding_model_ref: string;
    generation_model_ref: string;
    technique?: string;
    max_gaps?: number;
    max_spend_tokens?: number | null;
    top_k?: number;
    targets?: EnrichTarget[];
  }) => {
    setEnriching(true);
    try {
      const r = await enrichmentApi.autoEnrich(bookId, body, accessToken!);
      toast.success(t('gaps.enqueued', { count: r.enqueued_gaps ?? 0 }));
      qc.invalidateQueries({ queryKey: ['enrichment-jobs', bookId] });
      qc.invalidateQueries({ queryKey: ['enrichment-proposals', bookId] });
      return r;
    } catch (e) {
      toast.error((e as Error).message);
      return null;
    } finally {
      setEnriching(false);
    }
  };

  return { gaps, needsExtraction, detect, detecting, autoEnrich, enriching };
}
