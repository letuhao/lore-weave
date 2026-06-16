import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ArrowLeft } from 'lucide-react';

import { JobStatusBadge } from './JobStatusBadge';
import { JobProgress } from './JobProgress';
import { JobControls } from './JobControls';
import { JobChildrenTable } from './JobChildrenTable';
import { useJob } from '../hooks/useJob';
import { useJobLive } from '../context/JobsStreamProvider';
import { effectiveJob } from '../lib';
import { jobKey } from '../types';

/** Generic per-job detail (the cross-service generalization of CampaignMonitor).
 *  Campaign jobs are redirected to /campaigns/:id upstream; this renders the data
 *  jobs-service actually exposes (status, progress, detail_status, error, children).
 *  Live via the SSE overlay. */
export function JobMonitor({ service, jobId }: { service: string; jobId: string }) {
  const { t } = useTranslation('jobs');
  const detail = useJob(service, jobId);
  const live = useJobLive(jobKey({ service, job_id: jobId }));

  if (detail.isLoading)
    return <p className="text-sm text-muted-foreground">{t('list.loading', { defaultValue: 'Loading…' })}</p>;
  if (detail.error || !detail.data)
    return <p className="text-sm text-destructive">{t('monitor.error', { defaultValue: 'Failed to load job.' })}</p>;

  const job = effectiveJob(detail.data, live);
  const label = job.title || t(`kind.${job.kind}`, { defaultValue: job.kind });

  return (
    <div className="flex max-w-3xl flex-col gap-5">
      <Link to="/jobs" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-4 w-4" />
        {t('monitor.back', { defaultValue: 'All jobs' })}
      </Link>

      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 flex-col">
          <h1 className="truncate text-xl font-semibold">{label}</h1>
          <span className="text-[11px] text-muted-foreground">
            {job.service} · {t(`kind.${job.kind}`, { defaultValue: job.kind })}
          </span>
        </div>
        <JobStatusBadge status={job.status} />
      </div>

      {job.error && (
        <p className="rounded-md border border-destructive/40 bg-destructive/5 p-2 text-sm text-destructive">
          {job.error.message}
        </p>
      )}

      {job.status === 'paused' && (
        <p className="rounded-md border border-amber-500/40 bg-amber-500/5 p-2 text-sm text-amber-700 dark:text-amber-400">
          {t('monitor.pausedBanner', {
            defaultValue: 'Paused — no new units dispatch and in-flight ones finish. Resume below.',
          })}
        </p>
      )}

      <JobControls service={job.service} jobId={job.job_id} controlCaps={job.control_caps} />

      <JobProgress progress={job.progress} detailStatus={job.detail_status} />

      {(job.child_count ?? 0) > 0 && (
        <div className="rounded-lg border">
          <div className="border-b px-3 py-2 text-sm font-medium">
            {t('monitor.children', { defaultValue: 'Child jobs' })}
          </div>
          <JobChildrenTable parentJobId={job.job_id} />
        </div>
      )}
    </div>
  );
}
