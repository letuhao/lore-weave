import { useMemo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import {
  researchApi,
  isActiveResearchStatus,
  type CreateResearchJobReq,
  type ResearchJob,
} from '../researchApi';

/**
 * Controller for a kind's batch entity-research job (D-BATCH-RESEARCH-JOB). Lists the
 * book's research jobs, surfaces the latest one for the selected kind, and polls while it
 * is active so progress lands without a manual refresh. Owns create + lifecycle actions
 * (pause/resume/cancel); every mutation invalidates the list.
 */
export function useKindResearch(bookId: string, kindId: string | null) {
  const { accessToken } = useAuth();
  const qc = useQueryClient();
  const { t } = useTranslation('glossaryTiering');
  const key = ['research-jobs', bookId];

  const query = useQuery({
    queryKey: key,
    queryFn: () => researchApi.list(bookId, accessToken!),
    enabled: !!accessToken && !!bookId && !!kindId,
    refetchInterval: (q) =>
      ((q.state.data ?? []) as ResearchJob[]).some((j) => isActiveResearchStatus(j.status)) ? 2500 : false,
  });

  // The list is created_at DESC, so the first job for this kind is the newest.
  const job = useMemo<ResearchJob | null>(() => {
    if (!kindId || !query.data) return null;
    return query.data.find((j) => j.kind_id === kindId) ?? null;
  }, [query.data, kindId]);

  const invalidate = () => qc.invalidateQueries({ queryKey: key });

  const guard = async (fn: () => Promise<unknown>, okKey: string) => {
    try {
      await fn();
      toast.success(t(okKey));
      void invalidate();
    } catch (e) {
      toast.error((e as Error).message || t('research.toast.failed'));
    }
  };

  const create = async (req: CreateResearchJobReq) => {
    if (!kindId) return;
    await guard(() => researchApi.create(bookId, kindId, req, accessToken!), 'research.toast.started');
  };
  const pause = (jobId: string) => guard(() => researchApi.pause(bookId, jobId, accessToken!), 'research.toast.paused');
  const resume = (jobId: string) => guard(() => researchApi.resume(bookId, jobId, accessToken!), 'research.toast.resumed');
  const cancel = (jobId: string) => guard(() => researchApi.cancel(bookId, jobId, accessToken!), 'research.toast.cancelled');

  const estimate = (maxEntities: number) =>
    researchApi.estimate(bookId, kindId!, maxEntities, accessToken!);

  return { job, isLoading: query.isLoading, create, pause, resume, cancel, estimate };
}
