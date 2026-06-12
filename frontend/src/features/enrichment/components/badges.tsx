import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { tierOf, type Tier, type VerifyStatus } from '../types';

const PILL = 'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium';

const TIER_CLASS: Record<Tier, string> = {
  P1: 'bg-info/10 text-info',
  P2: 'bg-warning/12 text-warning',
  P3: 'bg-primary/12 text-primary',
};

/** P1 retrieval / P2 fabrication / P3 recook pill. */
export function TechniqueBadge({ technique }: { technique: string }) {
  const { t } = useTranslation('enrichment');
  const tier = tierOf(technique);
  const label = t(`technique.${technique}`, { defaultValue: technique });
  return (
    <span className={cn(PILL, TIER_CLASS[tier])} title={label}>
      {tier} · {label}
    </span>
  );
}

const VERIFY_CLASS: Record<string, string> = {
  verified_clean: 'bg-success/10 text-success',
  needs_review: 'bg-warning/12 text-warning',
  quarantined: 'bg-destructive/10 text-destructive',
  degraded: 'bg-secondary text-muted-foreground',
  auto_rejected: 'bg-destructive/10 text-destructive',
};

/** verified_clean / needs_review / quarantined / degraded / auto_rejected pill. */
export function VerifyBadge({ status }: { status?: VerifyStatus | string }) {
  const { t } = useTranslation('enrichment');
  if (!status) return null;
  return (
    <span className={cn(PILL, VERIFY_CLASS[status] ?? 'bg-secondary text-muted-foreground')}>
      {t(`verify.status.${status}`, { defaultValue: status })}
    </span>
  );
}

const REVIEW_CLASS: Record<string, string> = {
  proposed: 'bg-secondary text-muted-foreground',
  author_reviewing: 'bg-info/10 text-info',
  approved: 'bg-success/10 text-success',
  promoted: 'bg-primary/15 text-primary',
  rejected: 'bg-destructive/10 text-destructive',
};

export function ReviewStatusBadge({ status }: { status: string }) {
  const { t } = useTranslation('enrichment');
  return (
    <span className={cn(PILL, REVIEW_CLASS[status] ?? 'bg-secondary text-muted-foreground')}>
      {t(`review.${status}`, { defaultValue: status })}
    </span>
  );
}

/** The permanent H0 marker — an enriched variant ("dị bản"), never authored canon. */
export function H0Marker() {
  const { t } = useTranslation('enrichment');
  return (
    <span
      className={cn(PILL, 'border border-primary/30 bg-primary/5 text-primary')}
      title={t('h0.tooltip')}
      data-testid="enrichment-h0-marker"
    >
      ✦ {t('h0.marker')}
    </span>
  );
}
