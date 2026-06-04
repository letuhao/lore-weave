import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { enrichmentApi } from '../api';
import type { Job } from '../types';

const ACTIVE = new Set(['pending', 'estimating', 'running', 'paused']);

/** List the book's enrichment jobs + resume a cost-cap-paused one. Polls while any
 *  job is active so progress + new proposals surface without a manual refresh. */
export function useEnrichmentJobs(bookId: string) {
  const { accessToken } = useAuth();
  const qc = useQueryClient();
  const { t } = useTranslation('enrichment');

  const query = useQuery({
    queryKey: ['enrichment-jobs', bookId],
    queryFn: () => enrichmentApi.listJobs(bookId, accessToken!),
    enabled: !!accessToken && !!bookId,
    refetchInterval: (q) =>
      ((q.state.data?.items ?? []) as Job[]).some((j) => ACTIVE.has(j.status)) ? 4000 : false,
  });

  const resume = async (job: Job) => {
    try {
      await enrichmentApi.resumeJob(job.job_id, job.project_id, accessToken!);
      toast.success(t('jobs.resumed'));
      qc.invalidateQueries({ queryKey: ['enrichment-jobs', bookId] });
      qc.invalidateQueries({ queryKey: ['enrichment-proposals', bookId] });
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return {
    ...query,
    items: query.data?.items ?? [],
    total: query.data?.total ?? 0,
    resume,
  };
}
