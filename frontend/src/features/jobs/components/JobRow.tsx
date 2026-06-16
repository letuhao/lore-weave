import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ChevronDown, ChevronRight } from 'lucide-react';

import { JobStatusBadge } from './JobStatusBadge';
import { JobProgress } from './JobProgress';
import { JobControls } from './JobControls';
import { JobChildrenTable } from './JobChildrenTable';
import { useJobLive } from '../context/JobsStreamProvider';
import { effectiveJob } from '../lib';
import { jobKey, type Job } from '../types';

/** One job row in the dashboard. Reads its own live overlay (subscribes to just
 *  this key), deep-links campaigns to their existing monitor, and lazy-expands
 *  children under a parent (campaign). `nested` rows omit the expander/indent. */
export function JobRow({ job: base, nested }: { job: Job; nested?: boolean }) {
  const { t } = useTranslation('jobs');
  const job = effectiveJob(base, useJobLive(jobKey(base)));
  const [expanded, setExpanded] = useState(false);

  const hasChildren = !nested && (job.child_count ?? 0) > 0;
  const detailTo =
    job.kind === 'campaign'
      ? `/campaigns/${job.job_id}`
      : `/jobs/${encodeURIComponent(job.service)}/${encodeURIComponent(job.job_id)}`;
  const label = job.title || t(`kind.${job.kind}`, { defaultValue: job.kind });

  return (
    <div className={nested ? 'border-t' : 'rounded-lg border'}>
      <div className="flex items-center gap-3 p-3">
        {hasChildren ? (
          <button
            className="shrink-0 text-muted-foreground hover:text-foreground"
            onClick={() => setExpanded((v) => !v)}
            aria-label={t('list.toggleChildren', { defaultValue: 'Toggle children' })}
            aria-expanded={expanded}
          >
            {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          </button>
        ) : (
          !nested && <span className="w-4 shrink-0" />
        )}

        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <div className="flex items-center gap-2">
            <Link to={detailTo} className="truncate text-sm font-medium hover:underline">
              {label}
            </Link>
            <span className="shrink-0 text-[11px] text-muted-foreground">{job.service}</span>
            {hasChildren && (
              <span className="shrink-0 rounded-full bg-secondary px-1.5 text-[11px] text-muted-foreground">
                {job.child_count}
              </span>
            )}
          </div>
          <JobProgress progress={job.progress} detailStatus={job.detail_status} />
          {job.error && <span className="text-[11px] text-destructive">{job.error.message}</span>}
        </div>

        <JobStatusBadge status={job.status} />
        <JobControls service={job.service} jobId={job.job_id} controlCaps={job.control_caps} />
      </div>

      {expanded && hasChildren && <JobChildrenTable parentJobId={job.job_id} />}
    </div>
  );
}
