import { useTranslation } from 'react-i18next';
import type { CampaignStatus } from '../types';

const TONE: Record<CampaignStatus, string> = {
  created: 'bg-muted text-muted-foreground',
  running: 'bg-blue-500/15 text-blue-600 dark:text-blue-400',
  paused: 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
  completed: 'bg-green-500/15 text-green-600 dark:text-green-400',
  failed: 'bg-destructive/15 text-destructive',
  cancelling: 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
  cancelled: 'bg-muted text-muted-foreground',
};

/** Small status chip (view). Label is localized; falls back to the raw status. */
export function StatusBadge({ status }: { status: CampaignStatus }) {
  const { t } = useTranslation('campaigns');
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-medium ${TONE[status] ?? 'bg-muted'}`}>
      {t(`status.${status}`, { defaultValue: status })}
    </span>
  );
}
