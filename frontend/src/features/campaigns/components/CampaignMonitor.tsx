import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ArrowLeft } from 'lucide-react';
import { useCampaign, useCampaignProgress } from '../hooks/useCampaignQueries';
import { StatusBadge } from './StatusBadge';
import { SpentBudgetBar } from './SpentBudgetBar';
import { StageProgress } from './StageProgress';
import { ChapterProjectionTable } from './ChapterProjectionTable';
import { InFlightPanel } from './InFlightPanel';
import { ActivityLog } from './ActivityLog';
import { SwitchModelControl } from './SwitchModelControl';
import { MonitorControls } from './MonitorControls';
import { CampaignReport } from './CampaignReport';
import { deriveRunStats } from '../runStats';

const TERMINAL = ['completed', 'failed', 'cancelled'] as const;

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
  const terminal = (TERMINAL as readonly string[]).includes(liveStatus);

  // G3 — live run stats (elapsed / throughput / ETA / in-progress), derived from
  // started_at + the progress counts. Shown for active campaigns (terminal → report).
  const stats = progress.data
    ? (() => {
        const kn = progress.data.stages.knowledge;
        const tr = progress.data.stages.translation;
        // Dispatched stages = knowledge + translation (eval is observed). Settled =
        // done + skipped on each; total units ≈ 2 × chapters.
        const doneUnits = (kn.done + kn.skipped) + (tr.done + tr.skipped);
        return deriveRunStats({
          startedAt: c.started_at, finishedAt: c.finished_at, terminal,
          totalUnits: progress.data.total_chapters * 2,
          doneUnits,
          inProgress: kn.in_progress + tr.in_progress,
          nowMs: Date.now(),
        });
      })()
    : null;

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

      {/* #3 — paused-state guidance banner (graceful pause: in-flight drained, no partial writes). */}
      {liveStatus === 'paused' && (
        <p className="rounded-md border border-amber-500/40 bg-amber-500/5 p-2 text-sm text-amber-700 dark:text-amber-400">
          {t('monitor.pausedBanner', {
            defaultValue: 'Paused gracefully — no new chapters dispatch and in-flight ones finish (no partial writes, no extra spend). Resume below; if it auto-paused at the budget cap, raise the cap first.',
          })}
        </p>
      )}

      <MonitorControls campaignId={c.campaign_id} status={liveStatus} budgetUsd={budget} />

      {/* D-FACTORY-SWITCH-MODEL-RESUME — re-pick the LLM on a paused campaign, then resume. */}
      {liveStatus === 'paused' && <SwitchModelControl campaign={c} />}

      {/* G1 — wake-up report once terminal (outcome + spend-vs-estimate + error groups + review CTA). */}
      {terminal && <CampaignReport campaignId={c.campaign_id} bookId={c.book_id} />}

      {/* G3 — live run stats for an active campaign. */}
      {!terminal && stats && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            [stats.elapsed, t('monitor.elapsed', { defaultValue: 'elapsed' })],
            [stats.throughput, t('monitor.throughput', { defaultValue: 'throughput' })],
            [stats.eta, t('monitor.eta', { defaultValue: 'ETA (remaining)' })],
            [String(stats.inProgress), t('monitor.inFlight', { defaultValue: 'in progress' })],
          ].map(([v, label]) => (
            <div key={label} className="rounded-md border bg-secondary/40 p-3">
              <div className="text-lg font-semibold">{v}</div>
              <div className="text-[11px] text-muted-foreground">{label}</div>
            </div>
          ))}
        </div>
      )}

      <SpentBudgetBar spentUsd={spent} budgetUsd={budget} />

      {progress.data && <StageProgress stages={progress.data.stages} />}

      {/* D-FACTORY-INFLIGHT-PANEL — which chapters are dispatched right now (active only). */}
      <InFlightPanel campaignId={c.campaign_id} active={!terminal} />

      <ChapterProjectionTable
        campaignId={c.campaign_id}
        active={!terminal}
        hasFailures={
          !!progress.data &&
          Object.values(progress.data.stages).some((s) => s.failed > 0)
        }
      />

      {/* D-FACTORY-INFLIGHT-LOG — timestamped recent-activity feed (trigger-sourced). */}
      <ActivityLog campaignId={c.campaign_id} active={!terminal} />
    </div>
  );
}
