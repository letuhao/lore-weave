import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { JobSummaryCards } from '../JobSummaryCards';
import { FairnessBanner } from '../FairnessBanner';
import { JobsFilters } from '../JobsFilters';
import { JobStatusBadge } from '../JobStatusBadge';
import { JobProgress } from '../JobProgress';
import { JobControls } from '../JobControls';
import { JobCostTokens } from '../JobCostTokens';
import { HistoryPager } from '../HistoryPager';
import { useJobsDashboard } from '../../hooks/useJobsDashboard';
import { useJobLive, useJobsConnection } from '../../context/JobsStreamProvider';
import { effectiveJob } from '../../lib';
import { jobKey, type Job } from '../../types';

function JobCard({ job: base }: { job: Job }) {
  const { t } = useTranslation('jobs');
  const job = effectiveJob(base, useJobLive(jobKey(base)));
  const detailTo =
    job.kind === 'campaign'
      ? `/campaigns/${job.job_id}`
      : `/jobs/${encodeURIComponent(job.service)}/${encodeURIComponent(job.job_id)}`;
  const kindLabel = t(`kind.${job.kind}`, { defaultValue: job.kind });
  const label = job.title || kindLabel;

  return (
    <div className="flex flex-col gap-2 rounded-lg border bg-card p-3">
      <div className="flex items-start justify-between gap-2">
        <Link to={detailTo} className="min-w-0 truncate text-sm font-medium hover:underline">
          {label}
        </Link>
        <JobStatusBadge status={job.status} />
      </div>
      <span className="text-[11px] text-muted-foreground">
        {kindLabel} · {job.model ? `${job.service} · ${job.model}` : job.service}
      </span>
      <JobProgress progress={job.progress} detailStatus={job.detail_status} />
      <div className="flex items-center justify-between">
        <JobCostTokens job={job} />
        <JobControls service={job.service} jobId={job.job_id} controlCaps={job.control_caps} compact />
      </div>
    </div>
  );
}

/** Dedicated mobile dashboard: summary cards + filters + Active cards (live) +
 *  History cards (paginated). */
export function JobsMobile() {
  const { t } = useTranslation('jobs');
  const d = useJobsDashboard();
  const conn = useJobsConnection();

  const activeItems: Job[] = d.active.data?.pages.flatMap((p) => p.items) ?? [];
  const historyItems: Job[] = d.history.data?.items ?? [];
  const total = d.history.data?.total ?? 0;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">{t('title', { defaultValue: 'Jobs' })}</h1>
        <span className="text-[11px] text-muted-foreground">
          {conn === 'open' ? t('live.onShort', { defaultValue: 'live' }) : t('live.off', { defaultValue: 'offline' })}
        </span>
      </div>

      <JobSummaryCards summary={d.summary.data} selected={d.quick} onSelect={d.selectQuick} />
      <FairnessBanner />
      <JobsFilters kind={d.kind} onKind={d.changeKind} q={d.rawQ} onQ={d.changeQ} />

      {d.showActive && (
        <div className="flex flex-col gap-2">
          <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
            {t('section.active', { defaultValue: 'Active · live' })}
          </p>
          {activeItems.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t('list.noActive', { defaultValue: 'No active jobs.' })}</p>
          ) : (
            activeItems.map((j) => <JobCard key={jobKey(j)} job={j} />)
          )}
        </div>
      )}

      <div className="flex flex-col gap-2">
        <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
          {t('section.history', { defaultValue: 'History' })}
        </p>
        {d.history.isLoading ? (
          <p className="text-sm text-muted-foreground">{t('list.loading', { defaultValue: 'Loading…' })}</p>
        ) : historyItems.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('list.empty', { defaultValue: 'No jobs yet.' })}</p>
        ) : (
          historyItems.map((j) => <JobCard key={jobKey(j)} job={j} />)
        )}
      </div>

      <HistoryPager
        page={d.page}
        pageSize={d.pageSize}
        total={total}
        shown={historyItems.length}
        onPage={d.setPage}
        onPageSize={d.changePageSize}
      />
    </div>
  );
}
