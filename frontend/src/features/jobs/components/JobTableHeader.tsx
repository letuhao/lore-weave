import { useTranslation } from 'react-i18next';

import { JOB_GRID } from './jobGrid';

/** Column-header row for the desktop job tables (aligns with JobRow via JOB_GRID). */
export function JobTableHeader() {
  const { t } = useTranslation('jobs');
  return (
    <div className={`${JOB_GRID} border-b px-4 py-2.5 text-[11px] uppercase tracking-wide text-muted-foreground`}>
      <span />
      <span>{t('col.job', { defaultValue: 'Job' })}</span>
      <span>{t('col.status', { defaultValue: 'Status' })}</span>
      <span>{t('col.progress', { defaultValue: 'Progress' })}</span>
      <span>{t('col.cost', { defaultValue: 'Cost · tokens' })}</span>
      <span>{t('col.started', { defaultValue: 'Started' })}</span>
      <span>{t('col.actions', { defaultValue: 'Actions' })}</span>
    </div>
  );
}
