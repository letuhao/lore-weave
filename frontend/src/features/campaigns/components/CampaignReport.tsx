import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useCampaignReport } from '../hooks/useCampaignQueries';
import type { ErrorGroup } from '../types';

/** G1 — completion / wake-up report, shown by the monitor once a campaign is
 *  terminal (completed/failed/cancelled): outcome grid + spend-vs-estimate +
 *  error breakdown by cause + a "Review draft" CTA into the book's translation tab. */
export function CampaignReport({ campaignId, bookId }: { campaignId: string; bookId: string }) {
  const { t } = useTranslation('campaigns');
  const { data: r, isLoading, error } = useCampaignReport(campaignId);

  if (isLoading) return <p className="text-sm text-muted-foreground">{t('report.loading', { defaultValue: 'Loading report…' })}</p>;
  if (error || !r) return null;  // report is additive; if it fails the rest of the monitor still renders

  const translated = r.stages.translation?.done ?? 0;
  const errors = r.error_groups.reduce((n, g) => n + g.count, 0);
  const money = (v: string | null) => (v == null ? '—' : `$${Number(v).toFixed(2)}`);
  const estBand = r.est_usd_low != null && r.est_usd_high != null
    ? `${money(r.est_usd_low)}–${money(r.est_usd_high)}` : null;
  const dur = r.duration_seconds != null
    ? `${Math.floor(r.duration_seconds / 3600)}h${String(Math.floor((r.duration_seconds % 3600) / 60)).padStart(2, '0')}m` : '—';

  const causeLabel = (g: ErrorGroup) =>
    t(`report.cause.${g.cause}`, { defaultValue: g.cause.replace(/_/g, ' ') });

  return (
    <div className="flex flex-col gap-4 rounded-lg border p-4">
      <h2 className="text-sm font-semibold">{t('report.title', { defaultValue: 'Campaign report' })}</h2>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat value={String(translated)} label={t('report.translated', { defaultValue: 'translated' })} tone="ok" />
        <Stat value={String(errors)} label={t('report.errors', { defaultValue: 'errors (review)' })} tone={errors ? 'warn' : 'muted'} />
        <Stat value={money(r.spent_usd)} label={estBand ? t('report.spentVsEst', { defaultValue: 'spent (est {{band}})', band: estBand }) : t('report.spent', { defaultValue: 'spent' })} />
        <Stat value={dur} label={t('report.duration', { defaultValue: 'duration' })} />
      </div>

      {r.error_groups.length > 0 && (
        <table className="text-[12px]">
          <thead>
            <tr className="text-left text-muted-foreground">
              <th className="py-1 pr-4">{t('report.cause.h', { defaultValue: 'Cause' })}</th>
              <th className="py-1 pr-4">{t('report.count', { defaultValue: 'Chapters' })}</th>
              <th className="py-1">{t('report.fix', { defaultValue: 'Fix' })}</th>
            </tr>
          </thead>
          <tbody>
            {r.error_groups.map((g) => (
              <tr key={g.cause} className="border-t">
                <td className="py-1 pr-4 capitalize">{causeLabel(g)}</td>
                <td className="py-1 pr-4">{g.count}</td>
                <td className="py-1 text-muted-foreground">
                  {g.remediable
                    ? t('report.remediable', { defaultValue: 'Re-run likely fixes it' })
                    : t('report.notRemediable', { defaultValue: 'Source/data — re-run won’t help' })}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <Link
        to={`/books/${bookId}/translation`}
        className="self-start rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
      >
        {t('report.review', { defaultValue: 'Review draft' })}
      </Link>
    </div>
  );
}

function Stat({ value, label, tone }: { value: string; label: string; tone?: 'ok' | 'warn' | 'muted' }) {
  const color = tone === 'ok' ? 'text-green-600 dark:text-green-400'
    : tone === 'warn' ? 'text-amber-600 dark:text-amber-400' : '';
  return (
    <div className="rounded-md border bg-secondary/40 p-3">
      <div className={`text-lg font-semibold ${color}`}>{value}</div>
      <div className="text-[11px] text-muted-foreground">{label}</div>
    </div>
  );
}
