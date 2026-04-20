import { useState } from 'react';
import { Copy, Check } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { FormDialog } from '@/components/shared';
import type { ExtractionJobSummary } from '../types/projectState';

// K19a.5 — shared error viewer for `failed` + `building_paused_error` states.
// `failed` state carries only `error: string` (no job summary in the UI
// derivation), so `job` is optional; the dialog degrades to error-only when
// `job` is null. Used for root-cause inspection, not remediation — the
// retry/cancel buttons live on the card itself.

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  job: ExtractionJobSummary | null;
  error: string;
}

export function ErrorViewerDialog({ open, onOpenChange, job, error }: Props) {
  const { t } = useTranslation('knowledge');
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    // Clipboard API may be unavailable in insecure contexts (http://).
    // Fail silently — the error text is still visible on screen.
    void navigator.clipboard?.writeText(error).then(
      () => {
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1500);
      },
      () => {},
    );
  };

  return (
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      title={t('projects.errorViewer.title')}
      description={t('projects.errorViewer.description')}
      footer={
        <button
          type="button"
          onClick={() => onOpenChange(false)}
          className="rounded-md border px-3 py-1.5 text-sm font-medium hover:bg-secondary"
        >
          {t('projects.errorViewer.close')}
        </button>
      }
    >
      <div className="flex flex-col gap-3 text-sm">
        {job && (
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[12px]">
            <dt className="text-muted-foreground">{t('projects.errorViewer.jobIdLabel')}</dt>
            <dd className="font-mono">{job.job_id}</dd>
            <dt className="text-muted-foreground">{t('projects.errorViewer.startedLabel')}</dt>
            <dd>{job.started_at}</dd>
            <dt className="text-muted-foreground">{t('projects.errorViewer.scopeLabel')}</dt>
            <dd>{job.scope.kind}</dd>
            <dt className="text-muted-foreground">{t('projects.errorViewer.progressLabel')}</dt>
            <dd>
              {t('projects.errorViewer.progressValue', {
                processed: job.items_processed,
                total: job.items_total ?? '?',
              })}
            </dd>
            <dt className="text-muted-foreground">{t('projects.errorViewer.costLabel')}</dt>
            <dd>${job.cost_spent_usd}</dd>
          </dl>
        )}
        <div className="flex flex-col gap-1">
          <div className="flex items-center justify-between">
            <span className="text-[12px] font-medium text-muted-foreground">
              {t('projects.errorViewer.errorLabel')}
            </span>
            <button
              type="button"
              onClick={handleCopy}
              className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-muted-foreground hover:bg-secondary hover:text-foreground"
            >
              {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
              {copied
                ? t('projects.errorViewer.copied')
                : t('projects.errorViewer.copy')}
            </button>
          </div>
          <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-md border bg-muted/40 p-2 font-mono text-[12px] text-destructive">
            {error}
          </pre>
        </div>
      </div>
    </FormDialog>
  );
}
