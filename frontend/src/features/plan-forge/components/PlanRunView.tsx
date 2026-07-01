// The read-out for a plan run: status + artifacts + self-check gaps + validate report + a compile
// affordance (arc_id input). Render-only — all handlers come from the usePlanRun controller.
import { useState } from 'react';
import type {
  PlanCompileResult,
  PlanRunDetail,
  PlanSelfCheck,
  PlanValidateReport,
} from '../types';

interface Props {
  run: PlanRunDetail;
  polling: boolean;
  busy: boolean;
  selfCheck: PlanSelfCheck | null;
  validation: PlanValidateReport | null;
  compileResult: PlanCompileResult | null;
  onSelfCheck: () => void;
  onValidate: () => void;
  onCompile: (arcId: string) => void;
}

export function PlanRunView({
  run, polling, busy, selfCheck, validation, compileResult,
  onSelfCheck, onValidate, onCompile,
}: Props) {
  const [arcId, setArcId] = useState('');

  return (
    <div data-testid="plan-run-view" className="space-y-3 text-xs">
      <div className="flex items-center gap-2">
        <span className="font-medium text-foreground">Run</span>
        <span data-testid="plan-run-status" className="rounded-full bg-secondary px-2 py-0.5 text-[10px] uppercase text-muted-foreground">
          {run.status}
        </span>
        {polling && <span className="animate-pulse text-[10px] text-accent">working…</span>}
        <span className="ml-auto font-mono text-[10px] text-muted-foreground/60">{run.id.slice(0, 8)}</span>
      </div>

      {run.error_detail && (
        <p data-testid="plan-run-error" className="rounded bg-destructive/10 px-2 py-1 text-destructive">{run.error_detail}</p>
      )}

      {run.artifacts.length > 0 && (
        <div>
          <p className="mb-1 text-[10px] uppercase text-muted-foreground">Artifacts</p>
          <ul className="space-y-0.5">
            {run.artifacts.map((a) => (
              <li key={a.artifact_id} className="flex justify-between gap-2 rounded bg-muted/40 px-2 py-0.5">
                <span>{a.kind}</span>
                <span className="font-mono text-[10px] text-muted-foreground/60">{a.artifact_id.slice(0, 8)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex gap-2">
        <button
          type="button" data-testid="plan-selfcheck-btn" onClick={onSelfCheck} disabled={busy || polling}
          className="rounded border border-border px-2 py-1 hover:bg-secondary disabled:opacity-40"
        >Self-check</button>
        <button
          type="button" data-testid="plan-validate-btn" onClick={onValidate} disabled={busy || polling}
          className="rounded border border-border px-2 py-1 hover:bg-secondary disabled:opacity-40"
        >Validate</button>
      </div>

      {selfCheck && (
        <div data-testid="plan-selfcheck">
          <p className="mb-1 text-[10px] uppercase text-muted-foreground">
            Self-check · fidelity {selfCheck.fidelity_score != null ? selfCheck.fidelity_score.toFixed(2) : '—'}
          </p>
          {selfCheck.gaps.length === 0 ? (
            <p className="text-muted-foreground">No gaps.</p>
          ) : (
            <ul className="space-y-0.5">
              {selfCheck.gaps.map((g, i) => (
                <li key={`${g.path}-${i}`} className="rounded bg-muted/40 px-2 py-0.5">
                  <span className="mr-1 font-mono text-[10px] text-accent">{g.severity}</span>
                  <span className="text-muted-foreground">{g.path}</span> — {g.message}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {validation && (
        <div data-testid="plan-validation">
          <p className="mb-1 text-[10px] uppercase text-muted-foreground">
            Validate · {validation.passed ? 'passed' : 'failed'} · fidelity {validation.fidelity_score != null ? validation.fidelity_score.toFixed(2) : '—'}
          </p>
          <ul className="space-y-0.5">
            {validation.rules.map((r) => (
              <li key={r.id} className="rounded bg-muted/40 px-2 py-0.5">
                <span className={r.passed ? 'text-success' : 'text-destructive'}>{r.passed ? '✓' : '✗'}</span>{' '}
                <span className="text-muted-foreground">{r.id}</span> — {r.message}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="space-y-1 border-t pt-2">
        <p className="text-[10px] uppercase text-muted-foreground">Compile</p>
        <div className="flex gap-2">
          <input
            data-testid="plan-arc-input" value={arcId} onChange={(e) => setArcId(e.target.value)}
            placeholder="arc_id"
            className="flex-1 rounded border border-border bg-background px-1.5 py-1 text-xs outline-none focus:border-ring"
          />
          <button
            type="button" data-testid="plan-compile-btn" onClick={() => onCompile(arcId.trim())}
            disabled={busy || polling || !arcId.trim()}
            className="rounded bg-primary px-2 py-1 text-primary-foreground hover:brightness-110 disabled:opacity-40"
          >Compile</button>
        </div>
        {compileResult && (
          <p data-testid="plan-compile-result" className="text-[10px] text-muted-foreground">
            work {compileResult.work_id.slice(0, 8)} · pipeline {compileResult.pipeline_job_id.slice(0, 8)}
          </p>
        )}
      </div>
    </div>
  );
}
