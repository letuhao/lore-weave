// #20_agent_mode.md §3-7 (Mission control) — render-only; all logic lives in
// useMissionControl.
import { useTranslation } from 'react-i18next';
import { useMissionControl } from './useMissionControl';
import { RunHeader } from './RunHeader';
import { GateCheckPanel } from './GateCheckPanel';
import { UnitQueue } from './UnitQueue';
import { DiffReviewPanel } from './DiffReviewPanel';
import { RevertAllModal } from './RevertAllModal';

interface Props {
  bookId: string;
  runId: string | null;
  onBack: () => void;
}

export function MissionControlView({ bookId, runId, onBack }: Props) {
  const { t } = useTranslation('composition');
  const mc = useMissionControl(bookId, runId);

  if (!runId) {
    return (
      <div data-testid="agent-mode-mission-empty" className="flex h-full items-center justify-center p-6 text-center text-xs text-muted-foreground">
        {t('authoringRun.mission.empty', { defaultValue: 'Open a run from the Runs list to see its mission control.' })}
      </div>
    );
  }
  if (mc.runQuery.isLoading || !mc.run) {
    return <div className="p-3 text-xs text-muted-foreground">{t('authoringRun.mission.loading', { defaultValue: 'Loading run…' })}</div>;
  }

  const run = mc.run;
  const anyMutationBusy = mc.mutations.gate.isPending || mc.mutations.start.isPending
    || mc.mutations.pause.isPending || mc.mutations.resume.isPending || mc.mutations.close.isPending;

  return (
    <div className="p-3" data-testid="agent-mode-mission-control">
      <button type="button" onClick={onBack} data-testid="agent-mode-back-to-list" className="mb-2 text-[11px] text-muted-foreground hover:text-foreground">
        {t('authoringRun.mission.back', { defaultValue: '← Back to runs list' })}
      </button>

      <RunHeader
        run={run}
        busy={anyMutationBusy}
        startDisabledReason={mc.startDisabledReason}
        onAction={mc.runAction}
        onTogglePausePolicy={(next) => mc.mutations.setPausePolicy.mutate(next)}
        pausePolicyBusy={mc.mutations.setPausePolicy.isPending}
      />

      {run.status === 'gated' && <GateCheckPanel items={mc.gateChecks} />}

      {run.status !== 'draft' && (
        <div className="mb-3 rounded-md border p-3" data-testid="agent-mode-queue-panel">
          <h3 className="mb-2 text-[10.5px] font-semibold uppercase tracking-wide text-muted-foreground">
            {t('authoringRun.queue.title', { defaultValue: 'Unit queue' })} · {mc.queueRows.length}
          </h3>
          <UnitQueue rows={mc.queueRows} currentUnit={run.current_unit} selectedIndex={mc.selectedIndex} onSelect={mc.selectUnit} />
        </div>
      )}

      {mc.selectedIndex !== null && (
        <DiffReviewPanel
          bookId={bookId}
          runStatus={run.status}
          unit={mc.selectedUnitDetail}
          onAccept={mc.acceptSelected}
          onReject={mc.rejectSelected}
          onNav={mc.navUnit}
          onOpenFullDiff={mc.openFullDiff}
          reviewBusy={mc.reviewBusy}
        />
      )}

      <RevertAllModal
        open={mc.revertOpen}
        onOpenChange={mc.setRevertOpen}
        affected={mc.affectedForRevert}
        onConfirm={() => void mc.confirmRevert()}
        busy={mc.mutations.revertAll.isPending}
        result={mc.revertResult}
      />
    </div>
  );
}
