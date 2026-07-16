// PlanForge S3 (M4) — one row of the Pass Rail: number · name→output_kind · checkpoint + status
// badges · freshness · the context-dependent ACTION cell (run / blocked / running / awaiting review).
// Render-only; every handler comes from the panel. Module-level (never defined in a render body —
// that would remount the subtree on every parent render).
import { useTranslation } from 'react-i18next';
import type { PlanPass } from '../types';

interface Props {
  index: number;               // 1-based pass number
  pass: PlanPass;
  blockedAtHere: boolean;      // this is the blocking pass a human must accept next
  onRun: (passId: string) => void;   // open the cost-confirm for this pass
  onReview: (passId: string) => void; // open the checkpoint review (blocking + completed + pending)
  onView: (artifactId: string) => void; // PS-9 — open the pass artifact read-only
  disabled: boolean;
}

export function PassRow({ index, pass, blockedAtHere, onRun, onReview, onView, disabled }: Props) {
  const { t } = useTranslation('studio');
  const blocked = pass.blockers.length > 0;
  const running = pass.status === 'running' || (pass.status === 'pending' && !!pass.job_id);
  const completed = pass.status === 'completed';
  const failed = pass.status === 'failed';
  const awaitingReview =
    pass.checkpoint === 'blocking' && completed && pass.decision === 'pending';

  const freshness = !completed
    ? { label: '—', cls: 'text-muted-foreground/50' }
    : pass.fresh
      ? { label: t('planPasses.fresh', { defaultValue: 'fresh' }), cls: 'text-success' }
      : { label: t('planPasses.stale', { defaultValue: 'stale' }), cls: 'text-warning line-through' };

  return (
    <div
      data-testid={`pass-row-${pass.pass_id}`}
      className={`grid grid-cols-[1.4rem_1fr_auto_auto_auto_auto] items-center gap-2 rounded border px-2 py-1.5 ${
        blockedAtHere ? 'border-warning/60 bg-warning/5' : 'border-border'
      }`}
    >
      <span className="text-center font-mono text-[10px] text-muted-foreground/60">{index}</span>

      <span className="min-w-0">
        <span className="font-medium text-foreground">{pass.pass_id}</span>
        {/* PS-9 — a completed pass's output is readable (its content route is BE-3). */}
        {completed && pass.artifact_id ? (
          <button
            type="button" data-testid={`pass-view-${pass.pass_id}`} onClick={() => onView(pass.artifact_id as string)}
            className="ml-1 truncate text-[10px] text-accent-foreground underline hover:brightness-110"
          >→ {pass.output_kind} ↗</button>
        ) : (
          <span className="ml-1 truncate text-[10px] text-muted-foreground">→ {pass.output_kind}</span>
        )}
      </span>

      {/* checkpoint class */}
      {pass.checkpoint === 'blocking' ? (
        <span className="rounded bg-warning/15 px-1.5 py-0.5 text-[9px] font-semibold uppercase text-warning">
          {t('planPasses.blocking', { defaultValue: 'blocking' })}
        </span>
      ) : (
        <span className="rounded bg-secondary px-1.5 py-0.5 text-[9px] uppercase text-muted-foreground/70">
          {t('planPasses.advisory', { defaultValue: 'advisory' })}
        </span>
      )}

      {/* run status */}
      <span
        data-testid={`pass-status-${pass.pass_id}`}
        className={`text-[10px] ${failed ? 'text-destructive' : completed ? 'text-muted-foreground' : 'text-muted-foreground/50'}`}
      >
        {running
          ? t('planPasses.running', { defaultValue: 'running…' })
          : completed
            ? t('planPasses.done', { defaultValue: 'done' })
            : failed
              ? t('planPasses.failed', { defaultValue: 'failed' })
              : t('planPasses.notRun', { defaultValue: '— not run' })}
      </span>

      {/* freshness */}
      <span data-testid={`pass-fresh-${pass.pass_id}`} className={`text-[10px] ${freshness.cls}`}>
        {freshness.label}
      </span>

      {/* action */}
      <span className="justify-self-end">
        {running ? (
          <span className="animate-pulse text-[10px] text-accent">●</span>
        ) : awaitingReview ? (
          <button
            type="button" data-testid={`pass-review-${pass.pass_id}`} onClick={() => onReview(pass.pass_id)}
            className="rounded bg-warning/20 px-2 py-1 text-[11px] font-medium text-warning hover:bg-warning/30"
          >
            {t('planPasses.review', { defaultValue: 'review →' })}
          </button>
        ) : blocked ? (
          <span
            data-testid={`pass-blocked-${pass.pass_id}`}
            title={t('planPasses.blockedBy', {
              defaultValue: `blocked by: ${pass.blockers.join(', ')}`,
              blockers: pass.blockers.join(', '),
            })}
            className="rounded border border-border px-2 py-1 text-[10px] text-muted-foreground/60"
          >
            🔒 {t('planPasses.blocked', { defaultValue: 'blocked' })}
          </span>
        ) : (
          <button
            type="button" data-testid={`pass-run-${pass.pass_id}`} onClick={() => onRun(pass.pass_id)}
            disabled={disabled}
            className="rounded bg-primary px-2 py-1 text-[11px] font-medium text-primary-foreground hover:brightness-110 disabled:opacity-40"
          >
            {completed
              ? t('planPasses.rerun', { defaultValue: 're-run…' })
              : t('planPasses.run', { defaultValue: 'run…' })}
          </button>
        )}
      </span>
    </div>
  );
}
