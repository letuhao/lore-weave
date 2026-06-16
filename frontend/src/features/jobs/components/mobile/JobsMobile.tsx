import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { JobsFilters } from '../JobsFilters';
import { JobStatusBadge } from '../JobStatusBadge';
import { JobProgress } from '../JobProgress';
import { JobControls } from '../JobControls';
import { useJobsList } from '../../hooks/useJobsList';
import { useJobLive, useJobsConnection } from '../../context/JobsStreamProvider';
import { effectiveJob } from '../../lib';
import { jobKey, type Job, type JobListParams } from '../../types';

function JobCard({ job: base }: { job: Job }) {
  const { t } = useTranslation('jobs');
  const job = effectiveJob(base, useJobLive(jobKey(base)));
  const detailTo =
    job.kind === 'campaign'
      ? `/campaigns/${job.job_id}`
      : `/jobs/${encodeURIComponent(job.service)}/${encodeURIComponent(job.job_id)}`;
  const label = job.title || t(`kind.${job.kind}`, { defaultValue: job.kind });

  return (
    <div className="flex flex-col gap-2 rounded-lg border p-3">
      <div className="flex items-start justify-between gap-2">
        <Link to={detailTo} className="min-w-0 truncate text-sm font-medium hover:underline">
          {label}
        </Link>
        <JobStatusBadge status={job.status} />
      </div>
      <span className="text-[11px] text-muted-foreground">
        {job.service}
        {(job.child_count ?? 0) > 0 ? ` · ${job.child_count} ${t('mobile.children', { defaultValue: 'children' })}` : ''}
      </span>
      <JobProgress progress={job.progress} detailStatus={job.detail_status} />
      {job.error && <span className="text-[11px] text-destructive">{job.error.message}</span>}
      <JobControls service={job.service} jobId={job.job_id} controlCaps={job.control_caps} compact />
    </div>
  );
}

/** Dedicated mobile dashboard: a stacked card list (vs the desktop table rows). */
export function JobsMobile() {
  const { t } = useTranslation('jobs');
  const [filters, setFilters] = useState<JobListParams>({});
  const q = useJobsList(filters);
  const conn = useJobsConnection();
  const items: Job[] = q.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">{t('title', { defaultValue: 'Jobs' })}</h1>
        <span className="text-[11px] text-muted-foreground">
          {conn === 'open' ? t('live.on', { defaultValue: '● live' }) : t('live.off', { defaultValue: 'offline' })}
        </span>
      </div>
      <JobsFilters filters={filters} onChange={setFilters} />
      {q.isLoading ? (
        <p className="text-sm text-muted-foreground">{t('list.loading', { defaultValue: 'Loading…' })}</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('list.empty', { defaultValue: 'No jobs yet.' })}</p>
      ) : (
        <>
          {items.map((j) => (
            <JobCard key={jobKey(j)} job={j} />
          ))}
          {q.hasNextPage && (
            <button
              className="self-center rounded-lg border px-3 py-1.5 text-sm hover:bg-accent disabled:opacity-50"
              onClick={() => q.fetchNextPage()}
              disabled={q.isFetchingNextPage}
            >
              {t('list.more', { defaultValue: 'Load more' })}
            </button>
          )}
        </>
      )}
    </div>
  );
}
