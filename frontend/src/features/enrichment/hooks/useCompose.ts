import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { enrichmentApi } from '../api';
import type { ComposeBody, ResolvedIntent } from '../types';

/** Compose — start an enrichment job from a chosen input mode (slice 1: draft / gap).
 *  Async like auto-enrich: POST returns 202 + job_id, so on success we toast + refresh
 *  the jobs + proposals lists (the worker re-drives the job in the background). */
export function useCompose(bookId: string) {
  const { accessToken } = useAuth();
  const qc = useQueryClient();
  const { t } = useTranslation('enrichment');
  const [composing, setComposing] = useState(false);
  const [resolving, setResolving] = useState(false);

  const compose = async (body: ComposeBody) => {
    setComposing(true);
    try {
      const r = await enrichmentApi.compose(bookId, body, accessToken!);
      toast.success(t('compose.enqueued'));
      qc.invalidateQueries({ queryKey: ['enrichment-jobs', bookId] });
      qc.invalidateQueries({ queryKey: ['enrichment-proposals', bookId] });
      return r;
    } catch (e) {
      toast.error((e as Error).message);
      return null;
    } finally {
      setComposing(false);
    }
  };

  /** Mode B step 1: resolve a free-text intent → a proposed target (no job). Returns
   *  the proposal for the FE to confirm/edit, or null on error (toasted). */
  const resolveIntent = async (intentText: string, genModel: string): Promise<ResolvedIntent | null> => {
    setResolving(true);
    try {
      return await enrichmentApi.resolveIntent(bookId, intentText, genModel, accessToken!);
    } catch (e) {
      toast.error((e as Error).message);
      return null;
    } finally {
      setResolving(false);
    }
  };

  return { compose, composing, resolveIntent, resolving };
}
