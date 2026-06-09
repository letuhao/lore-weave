import { useEffect, useRef, useState, useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { wikiApi } from '../api';
import type { WikiGenJobStatus, WikiGenerateResult } from '../types';

const POLL_MS = 2_000;

export interface TriggerArgs {
  model_ref?: string;
  model_source?: string;
  kind_codes?: string[];
  max_spend_usd?: number;
}

/**
 * wiki-llm M7b-2a — the wiki LLM-generation job controller.
 *
 * Owns the whole job lifecycle for one book: polls the latest job
 * (`GET …/wiki/job`, 2s while pending|running, off otherwise — 404 = no job →
 * null), triggers generation (deterministic stub vs LLM delegate), and
 * resumes/cancels. When a run reaches `complete` it invalidates the article
 * list so freshly-generated articles appear without a manual refresh.
 */
export function useWikiGenJob(bookId: string) {
  const { accessToken } = useAuth();
  const { t } = useTranslation('wiki');
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);

  const jobQuery = useQuery<WikiGenJobStatus | null>({
    queryKey: ['wiki-gen-job', bookId],
    enabled: !!accessToken,
    retry: false,
    queryFn: async () => {
      try {
        return await wikiApi.getJob(bookId, accessToken!);
      } catch (e) {
        // 404 = no job has ever run for this book → a first-class "idle" state,
        // not an error. Any other status is a real failure → surface it.
        if ((e as { status?: number }).status === 404) return null;
        throw e;
      }
    },
    // Poll only while the job is in flight; a terminal/idle job needs no polling
    // (a fresh trigger invalidates this query and restarts the cycle).
    refetchInterval: (query) => {
      const s = query.state.data?.status;
      return s === 'pending' || s === 'running' ? POLL_MS : false;
    },
  });

  const job = jobQuery.data ?? null;
  const isActive = job?.status === 'pending' || job?.status === 'running';

  // Sync the article list to the polled job state: when a run completes, the
  // new articles exist server-side but the cached list predates them. This is a
  // synchronization concern (server state changed under us via polling), not the
  // forbidden "react to a state change with an effect" anti-pattern. Guarded by
  // a per-job ref so it fires once per completed job, not every poll tick.
  const invalidatedFor = useRef<string | null>(null);
  useEffect(() => {
    if (job?.status === 'complete' && invalidatedFor.current !== job.job_id) {
      invalidatedFor.current = job.job_id;
      queryClient.invalidateQueries({ queryKey: ['wiki-articles', bookId] });
    }
  }, [job?.status, job?.job_id, bookId, queryClient]);

  const refetchJob = useCallback(
    () => queryClient.invalidateQueries({ queryKey: ['wiki-gen-job', bookId] }),
    [queryClient, bookId],
  );

  /**
   * Fire a generate request. Resolves on success (caller closes the dialog),
   * throws on failure (caller keeps it open). All user-facing toasts live here.
   */
  const trigger = useCallback(
    async (args: TriggerArgs): Promise<WikiGenerateResult> => {
      if (!accessToken) throw new Error('no auth');
      setBusy(true);
      try {
        const result = await wikiApi.generateStubs(
          bookId,
          {
            ...(args.kind_codes?.length ? { kind_codes: args.kind_codes } : {}),
            ...(args.model_ref
              ? {
                  model_ref: args.model_ref,
                  model_source: args.model_source || 'user_model',
                  ...(args.max_spend_usd != null ? { max_spend_usd: args.max_spend_usd } : {}),
                }
              : {}),
          },
          accessToken,
        );
        if ('job_id' in result) {
          toast.success(t('gen.started'));
          await refetchJob(); // begin polling the new job immediately
        } else if ('action' in result) {
          toast.info(t('gen.noEntities'));
        } else {
          // deterministic stubs
          if (result.created > 0) {
            toast.success(t('generatedCount', { count: result.created }));
            queryClient.invalidateQueries({ queryKey: ['wiki-articles', bookId] });
          } else {
            toast.info(t('generatedNone'));
          }
        }
        return result;
      } catch (e) {
        const status = (e as { status?: number }).status;
        if (status === 409) {
          // An active job already holds the per-book lock — surface it (the
          // banner shows its progress) rather than a generic failure.
          toast.info(t('gen.alreadyRunning'));
          await refetchJob();
        } else if (status === 404) {
          toast.error(t('gen.notIndexed'));
        } else {
          toast.error(t('generateFailed'));
        }
        throw e;
      } finally {
        setBusy(false);
      }
    },
    [accessToken, bookId, t, refetchJob, queryClient],
  );

  const resume = useCallback(async () => {
    if (!accessToken || !job) return;
    setBusy(true);
    try {
      await wikiApi.resumeJob(bookId, job.job_id, accessToken);
      toast.success(t('gen.resumed'));
      await refetchJob();
    } catch {
      toast.error(t('gen.resumeFailed'));
    } finally {
      setBusy(false);
    }
  }, [accessToken, bookId, job, t, refetchJob]);

  const cancel = useCallback(async () => {
    if (!accessToken || !job) return;
    setBusy(true);
    try {
      await wikiApi.cancelJob(bookId, job.job_id, accessToken);
      toast.success(t('gen.cancelled'));
      await refetchJob();
    } catch {
      toast.error(t('gen.cancelFailed'));
    } finally {
      setBusy(false);
    }
  }, [accessToken, bookId, job, t, refetchJob]);

  return { job, isActive, busy, trigger, resume, cancel };
}
