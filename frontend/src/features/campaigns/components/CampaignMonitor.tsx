import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ArrowLeft } from 'lucide-react';
import { useCampaign, useCampaignProgress } from '../hooks/useCampaignQueries';
import { StatusBadge } from './StatusBadge';
import { SpentBudgetBar } from './SpentBudgetBar';
import { StageProgress } from './StageProgress';
import { ChapterProjectionTable } from './ChapterProjectionTable';
import { MonitorControls } from './MonitorControls';

/** S6 — the live campaign monitor (replaces the S5c read-only detail). The
 *  lightweight progress query drives the header bars (polls 6s while active); the
 *  heavier chapters[] detail polls slowly (15s) for the projection table. */
export function CampaignMonitor({ campaignId }: { campaignId: string }) {
  const { t } = useTranslation('campaigns');
  const detail = useCampaign(campaignId, true);
  const progress = useCampaignProgress(campaignId);

  if (detail.isLoading) return <p className="text-sm text-muted-foreground">{t('monitor.loading', { defaultValue: 'Loading…' })}</p>;
  if (detail.error || !detail.data) return <p className="text-sm text-destructive">{t('monitor.error', { defaultValue: 'Failed to load campaign.' })}</p>;

  const c = detail.data;
  const liveStatus = progress.data?.status ?? c.status;
  const spent = progress.data?.spent_usd ?? c.spent_usd;
  const budget = progress.data?.budget_usd ?? c.budget_usd;

  return (
    <div className="flex max-w-3xl flex-col gap-5">
      <Link to="/campaigns" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-4 w-4" />{t('monitor.back', { defaultValue: 'All campaigns' })}
      </Link>

      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">{c.name}</h1>
        <StatusBadge status={liveStatus} />
      </div>

      {c.error_message && (
        <p className="rounded-md border border-destructive/40 bg-destructive/5 p-2 text-sm text-destructive">
          {c.error_message}
        </p>
      )}

      <MonitorControls campaignId={c.campaign_id} status={liveStatus} budgetUsd={budget} />

      <SpentBudgetBar spentUsd={spent} budgetUsd={budget} />

      {progress.data && <StageProgress stages={progress.data.stages} />}

      <ChapterProjectionTable chapters={c.chapters} />
    </div>
  );
}
