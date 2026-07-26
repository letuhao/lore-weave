import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ChevronDown, ChevronRight } from 'lucide-react';

import { JobStatusBadge } from './JobStatusBadge';
import { JobProgress } from './JobProgress';
import { JobControls } from './JobControls';
import { JobCostTokens } from './JobCostTokens';
import { JobChildrenTable } from './JobChildrenTable';
import { JOB_GRID } from './jobGrid';
import { useJobLive } from '../context/JobsStreamProvider';
import { effectiveJob, formatRelative, formatDuration } from '../lib';
import { isTerminal, jobKey, type Job } from '../types';

/** One desktop grid row. Reads its own live overlay (subscribes to just this key),
 *  deep-links campaigns to their monitor, and lazy-expands children under a parent.
 *  `nested` (child) rows drop the expander and indent the Job cell.
 *
 *  `onOpenDetail` (studio dockable-migration injectable prop, docs/standards/dockable-gui.md
 *  U3): when provided (the studio JobsListPanel), row/detail clicks call it instead of
 *  rendering a route `<Link>` — the panel opens `job-detail` as a sibling dock tab rather than
 *  navigating away. Omitted (the standalone /jobs page): behavior is byte-identical to before. */
export function JobRow({
  job: base,
  nested,
  onOpenDetail,
}: {
  job: Job;
  nested?: boolean;
  onOpenDetail?: (service: string, jobId: string) => void;
}) {
  const { t } = useTranslation('jobs');
  const job = effectiveJob(base, useJobLive(jobKey(base)));
  const [expanded, setExpanded] = useState(false);

  const hasChildren = !nested && (job.child_count ?? 0) > 0;
  const detailTo =
    job.kind === 'campaign'
      ? `/campaigns/${job.job_id}`
      : `/jobs/${encodeURIComponent(job.service)}/${encodeURIComponent(job.job_id)}`;
  const kindLabel = t(`kind.${job.kind}`, { defaultValue: job.kind });
  const label = job.title || kindLabel;
  const subtitle = job.model ? `${job.service} · ${job.model}` : job.service;
  const terminal = isTerminal(job.status);
  const started = formatRelative(job.created_at);
  const duration = formatDuration(job.created_at, job.updated_at);
  const openDetail = () => onOpenDetail?.(job.service, job.job_id);
  // /review-impl HIGH fix: onOpenDetail must never override the campaign deep-link — job-detail
  // (JobMonitor) explicitly assumes it's never reached for a campaign job (see its own header
  // comment: "Campaign jobs redirect to /campaigns/:id upstream"). A campaign row keeps the real
  // <Link> even when the studio panel supplies onOpenDetail.
  const useCallbackNav = Boolean(onOpenDetail) && job.kind !== 'campaign';

  return (
    <div className={nested ? 'bg-muted/20' : ''}>
      <div className={`${JOB_GRID} border-b px-4 py-3 hover:bg-accent/30`}>
        {/* col 1 — expander */}
        {hasChildren ? (
          <button
            type="button"
            className="text-center text-muted-foreground hover:text-foreground"
            onClick={() => setExpanded((v) => !v)}
            aria-label={t('list.toggleChildren', { defaultValue: 'Toggle children' })}
            aria-expanded={expanded}
          >
            {expanded ? <ChevronDown className="mx-auto h-4 w-4" /> : <ChevronRight className="mx-auto h-4 w-4" />}
          </button>
        ) : (
          <span />
        )}

        {/* col 2 — job: title + kind badge + service·model */}
        <div className={`min-w-0 ${nested ? 'pl-3' : ''}`}>
          {useCallbackNav ? (
            <button
              type="button"
              onClick={openDetail}
              className={`block truncate text-left font-medium hover:underline ${nested ? 'text-sm' : ''}`}
            >
              {label}
            </button>
          ) : (
            <Link to={detailTo} className={`block truncate font-medium hover:underline ${nested ? 'text-sm' : ''}`}>
              {label}
            </Link>
          )}
          <div className="mt-0.5 flex items-center gap-2">
            <span className="rounded-full bg-secondary px-1.5 py-0.5 text-[11px] text-muted-foreground">
              {kindLabel}
            </span>
            <span className="truncate text-[11px] text-muted-foreground">{subtitle}</span>
            {hasChildren && (
              <span className="shrink-0 rounded-full bg-secondary px-1.5 text-[11px] text-muted-foreground">
                {job.child_count}
              </span>
            )}
          </div>
        </div>

        {/* col 3 — status */}
        <JobStatusBadge status={job.status} />

        {/* col 4 — progress (or error for failed rows) */}
        <div className="min-w-0">
          {job.error && terminal ? (
            <span className="truncate text-xs text-destructive">{job.error.message}</span>
          ) : (
            <JobProgress progress={job.progress} detailStatus={job.detail_status} />
          )}
        </div>

        {/* col 5 — cost · tokens */}
        <JobCostTokens job={job} />

        {/* col 6 — started + duration */}
        <div className="text-xs text-muted-foreground">
          {started ?? '—'}
          {duration && (
            <>
              <br />
              <span className="text-[11px]">
                {terminal
                  ? t('row.ran', { defaultValue: 'ran {{d}}', d: duration })
                  : t('row.running', { defaultValue: 'running {{d}}', d: duration })}
              </span>
            </>
          )}
        </div>

        {/* col 7 — actions */}
        <div className="flex flex-wrap items-center gap-1.5">
          <JobControls service={job.service} jobId={job.job_id} controlCaps={job.control_caps} compact />
          {useCallbackNav ? (
            <button
              type="button"
              onClick={openDetail}
              className="inline-flex items-center rounded-lg px-2 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              {t('row.details', { defaultValue: 'Details ↗' })}
            </button>
          ) : (
            <Link
              to={detailTo}
              className="inline-flex items-center rounded-lg px-2 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              {t('row.details', { defaultValue: 'Details ↗' })}
            </Link>
          )}
        </div>
      </div>

      {expanded && hasChildren && <JobChildrenTable parentJobId={job.job_id} />}
    </div>
  );
}
