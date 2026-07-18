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
  /** BYOK model for the Tier-W re-run (composition_conformance_run). No model ⇒ the Re-run
   *  button is disabled with a hint; the read + regenerate still work. */
  modelRef?: string | null;
  /** §2#6 loop-connect — deep-link to the scene-inspector for a scene (to bind/fix a beat). The
   *  host-owning panel wires it to host.publish + openPanel('scene-inspector'). */
  onOpenScene?: (sceneId: string, chapterId: string) => void;
};

export function ConformanceTraceView({ projectId, chapterId, token, modelRef, onOpenScene }: Props) {
  const { t } = useTranslation('composition');
  const trace = useConformanceTrace(projectId, chapterId, token, modelRef);
  const conf = trace.conformance;
  const scenes = conf?.scenes ?? [];
  const isEmpty = !trace.isLoading && !trace.isError && scenes.length === 0;
  // The reader emits no chapter-level conform_count — derive [conforming, judged]
  // from the per-scene verdicts (a scene counts only once both binary flags resolved).
  const judged = scenes.filter(
    (s) => s.conformance && typeof s.conformance.beat_realized === 'boolean' && typeof s.conformance.tension_band_match === 'boolean',
  );
  const conforming = judged.filter((s) => s.conformance!.beat_realized && s.conformance!.tension_band_match).length;

  return (
    <div data-testid="conformance-trace-view" className="flex h-full flex-col gap-2 overflow-auto p-2">
      <div className="flex items-center justify-between gap-2">
        <div className="text-sm font-medium text-neutral-800 dark:text-neutral-100">
          {t('motif.conf.title', { defaultValue: 'Conformance' })}
          {/* FE-derived [conforming/judged] count (the reader emits no conform_count). */}
          {judged.length > 0 && (
            <span className="ml-2 text-xs text-neutral-500" data-testid="conformance-count">{conforming}/{judged.length}</span>
          )}
        </div>
        <button
          type="button"
          data-testid="conformance-rerun"
          className="rounded border border-amber-400 px-2 py-0.5 text-xs text-amber-700 disabled:opacity-50 dark:text-amber-300"
          disabled={!projectId || !chapterId || !trace.canRerun || trace.mintRun.isPending}
          title={!trace.canRerun ? t('motif.conf.rerunNeedsModel', { defaultValue: 'Pick a model to re-run conformance' }) : undefined}
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
          <div data-testid="conformance-empty" className="p-4 text-center text-xs text-neutral-500">
            <p>{t('motif.conf.empty', { defaultValue: 'Not generated yet — generate scenes to see conformance.' })}</p>
            {/* §2#6 loop-connect — the empty state is a dead-end without a next step; deep-link to the
                scene-inspector where a motif is bound to a scene (spec 33 §3.4). */}
            {onOpenScene && chapterId && (
              <button
                type="button"
                data-testid="conformance-empty-bind-cta"
                onClick={() => onOpenScene('', chapterId)}
                className="mt-2 rounded border border-amber-400 px-2 py-0.5 text-[11px] text-amber-700 hover:bg-amber-50 dark:text-amber-300 dark:hover:bg-amber-950/30"
              >
                {t('motif.conf.bindCta', { defaultValue: 'Bind a motif to a scene →' })}
              </button>
            )}
          </div>
        ) : (
          <div>
            {scenes.map((s) => (
              <ConformanceSceneRow
                key={s.outline_node_id}
                scene={s}
                onRegenerate={(id) => trace.regenerateScene.mutate(id)}
                onOpenScene={onOpenScene && chapterId ? (sid) => onOpenScene(sid, chapterId) : undefined}
              />
            ))}
          </div>
        )}
      </MotifStateBoundary>
    </div>
  );
}
