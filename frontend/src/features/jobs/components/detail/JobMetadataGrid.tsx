import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Copy } from 'lucide-react';

import type { Job } from '../../types';
import { formatRelative } from '../../lib';

/** Metadata grid: job id (copyable) · kind · service · parent link · created · last
 *  update. Created/updated show absolute + relative. */
export function JobMetadataGrid({ job }: { job: Job }) {
  const { t } = useTranslation('jobs');

  const copyId = async () => {
    try {
      await navigator.clipboard.writeText(job.job_id);
      toast.success(t('detail.copied', { defaultValue: 'Job ID copied.' }));
    } catch {
      toast.error(t('detail.copyFailed', { defaultValue: 'Could not copy.' }));
    }
  };

  const cell = (labelKey: string, def: string, body: React.ReactNode) => (
    <div>
      <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
        {t(labelKey, { defaultValue: def })}
      </div>
      <div className="mt-0.5 text-sm">{body}</div>
    </div>
  );

  const when = (iso: string | null) =>
    iso ? `${iso.replace('T', ' ').slice(0, 16)} · ${formatRelative(iso)}` : '—';

  return (
    <div className="grid grid-cols-2 gap-4 rounded-xl border bg-card p-4 sm:grid-cols-3">
      {cell(
        'detail.jobId',
        'Job ID',
        <button type="button" onClick={copyId} className="inline-flex items-center gap-1 font-mono text-xs hover:text-foreground">
          {job.job_id.slice(0, 8)}…{job.job_id.slice(-5)}
          <Copy className="h-3 w-3" />
        </button>,
      )}
      {cell('detail.kind', 'Kind', t(`kind.${job.kind}`, { defaultValue: job.kind }))}
      {cell('detail.service', 'Service', job.service)}
      {job.parent_job_id &&
        cell(
          'detail.parent',
          'Parent',
          <Link to={`/campaigns/${job.parent_job_id}`} className="text-accent-foreground hover:underline">
            {t('detail.viewParent', { defaultValue: 'View parent ↗' })}
          </Link>,
        )}
      {cell('detail.created', 'Created', when(job.created_at))}
      {cell('detail.lastUpdate', 'Last update', when(job.updated_at))}
    </div>
  );
}
