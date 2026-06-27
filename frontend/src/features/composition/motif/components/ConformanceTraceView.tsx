// W6 §3.4 (mockup 07-A) — the conformance DOCK PANEL. Coarse chapter-scope only
// (P1; the arc-level dashboard 07-B is P4/W10). Orchestrates the scene rows + the
// Tier-W re-run confirm + the empty/loading/error states. Holds no logic.
import { useTranslation } from 'react-i18next';
import { MotifStateBoundary } from './MotifStateBoundary';
import { ConformanceSceneRow } from './ConformanceSceneRow';
import { CostConfirmCard } from './CostConfirmCard';
import { useConformanceTrace } from '../hooks/useConformanceTrace';

type Props = {
  projectId: string | undefined;
  chapterId: string | undefined;
  token: string | null;
};

export function ConformanceTraceView({ projectId, chapterId, token }: Props) {
  const { t } = useTranslation('composition');
  const trace = useConformanceTrace(projectId, chapterId, token);
  const conf = trace.conformance;
  const isEmpty = !trace.isLoading && !trace.isError && (!conf || conf.scenes.length === 0);

  return (
    <div data-testid="conformance-trace-view" className="flex h-full flex-col gap-2 overflow-auto p-2">
      <div className="flex items-center justify-between gap-2">
        <div className="text-sm font-medium text-neutral-800 dark:text-neutral-100">
          {t('motif.conf.title', { defaultValue: 'Conformance' })}
          {/* conform_count is summary-only; the chapter reader (GET …/conformance)
              does NOT emit it today (D-MOTIF-CONFORMANCE-CONTRACT). Guard the array
              access so a missing field degrades the header to no-count instead of
              white-screening the whole studio (the panel is always-mounted). */}
          {Array.isArray(conf?.conform_count) && (
            <span className="ml-2 text-xs text-neutral-500">{conf.conform_count[0]}/{conf.conform_count[1]}</span>
          )}
        </div>
        <button
          type="button"
          data-testid="conformance-rerun"
          className="rounded border border-amber-400 px-2 py-0.5 text-xs text-amber-700 disabled:opacity-50 dark:text-amber-300"
          disabled={!projectId || !chapterId || trace.mintRun.isPending}
          onClick={() => trace.mintRun.mutate()}
        >
          {t('motif.conf.rerun', { defaultValue: 'Re-run' })}
        </button>
      </div>

      {/* Tier-W re-run confirm (mint→confirm) */}
      {trace.estimate && (
        <CostConfirmCard
          estimate={trace.estimate}
          whatItDoes={t('motif.conf.rerunWhat', { defaultValue: 'Re-check every scene in this chapter against its planned beat.' })}
          confirming={trace.confirmRun.isPending}
          onConfirm={() => trace.confirmRun.mutate()}
          onCancel={trace.cancelRun}
        />
      )}

      <MotifStateBoundary isLoading={trace.isLoading} isError={trace.isError} onRetry={() => trace.refetch()} skeleton="rows">
        {isEmpty ? (
          <p data-testid="conformance-empty" className="p-4 text-center text-xs text-neutral-500">
            {t('motif.conf.empty', { defaultValue: 'Not generated yet — generate scenes to see conformance.' })}
          </p>
        ) : (
          <div>
            {(conf?.scenes ?? []).map((s) => (
              <ConformanceSceneRow key={s.outline_node_id} scene={s} onRegenerate={(id) => trace.regenerateToBeat.mutate(id)} />
            ))}
          </div>
        )}
      </MotifStateBoundary>
    </div>
  );
}
