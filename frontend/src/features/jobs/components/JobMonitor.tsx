import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ArrowLeft } from 'lucide-react';

import { JobStatusBadge } from './JobStatusBadge';
import { JobControls } from './JobControls';
import { JobChildrenTable } from './JobChildrenTable';
import { JobTableHeader } from './JobTableHeader';
import { JobProgressPanel } from './detail/JobProgressPanel';
import { JobCostUsagePanel } from './detail/JobCostUsagePanel';
import { JobParametersPanel } from './detail/JobParametersPanel';
import { JobMetadataGrid } from './detail/JobMetadataGrid';
import { JobActivityTimeline } from './detail/JobActivityTimeline';
import { useJob } from '../hooks/useJob';
import { useJobLive } from '../context/JobsStreamProvider';
import { effectiveJob } from '../lib';
import { jobKey } from '../types';

/** Generic per-job detail (the cross-service generalization of CampaignMonitor).
 *  Campaign jobs redirect to /campaigns/:id upstream; this renders the unified
 *  projection: progress · cost & usage · dynamic parameters · metadata · activity ·
 *  children · error. Live via the SSE overlay. */
export function JobMonitor({ service, jobId }: { service: string; jobId: string }) {
  const { t } = useTranslation('jobs');
  const detail = useJob(service, jobId);
  const live = useJobLive(jobKey({ service, job_id: jobId }));

  if (detail.isLoading)
    return <p className="text-sm text-muted-foreground">{t('list.loading', { defaultValue: 'Loading…' })}</p>;
  if (detail.error || !detail.data)
    return <p className="text-sm text-destructive">{t('monitor.error', { defaultValue: 'Failed to load job.' })}</p>;

  const job = effectiveJob(detail.data, live);
  const kindLabel = t(`kind.${job.kind}`, { defaultValue: job.kind });
  const label = job.title || kindLabel;
  const isFailed = job.status === 'failed';

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-4">
      <Link to="/jobs" className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-4 w-4" />
        {t('monitor.back', { defaultValue: 'All jobs' })}
      </Link>

      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="truncate text-2xl font-semibold">{label}</h1>
          <div className="mt-2 flex items-center gap-2">
            <span className="rounded-full bg-secondary px-1.5 py-0.5 text-[11px] text-muted-foreground">{kindLabel}</span>
            <span className="text-[11px] text-muted-foreground">{job.service}</span>
            <JobStatusBadge status={job.status} />
          </div>
        </div>
        <JobControls service={job.service} jobId={job.job_id} controlCaps={job.control_caps} />
      </div>

      {job.status === 'paused' && (
        <p className="rounded-md border border-amber-500/40 bg-amber-500/5 p-2 text-sm text-amber-700 dark:text-amber-400">
          {t('monitor.pausedBanner', {
            defaultValue: 'Paused — no new units dispatch and in-flight ones finish. Resume above.',
          })}
        </p>
      )}

      <JobProgressPanel job={job} />
      <JobCostUsagePanel job={job} />
      <JobParametersPanel params={job.params} />
      <JobMetadataGrid job={job} />
      <JobActivityTimeline job={job} />

      {(job.child_count ?? 0) > 0 && (
        <div className="overflow-hidden rounded-xl border bg-card">
          <div className="border-b px-4 py-3 text-sm font-semibold">
            {t('monitor.children', { defaultValue: 'Child jobs' })} · {job.child_count}
          </div>
          <JobTableHeader />
          <JobChildrenTable parentJobId={job.job_id} />
        </div>
      )}

      {isFailed && job.error && (
        <div className="rounded-xl border bg-card">
          <div className="border-b px-4 py-3 text-sm font-semibold">
            {t('detail.errorTitle', { defaultValue: 'Error' })}
          </div>
          <div className="p-4">
            <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
              <b>{job.error.code}</b>
              <br />
              {job.error.message}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
