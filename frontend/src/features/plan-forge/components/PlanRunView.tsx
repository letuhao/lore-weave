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
  /** PS-9 — open one artifact read-only in the json-editor (fed by BE-3). */
  onOpenArtifact: (artifactId: string) => void;
  // ⑨ Repair strip — appears ONLY when self-check found gaps (recovery tools are meaningless
  // without a diagnosis; an always-on row of three paid buttons is a leaky abstraction).
  repairOutput: string | null;
  canRepair: boolean; // a chat model is chosen and nothing is in flight
  onExplain: () => void;
  onApplyFix: () => void;
  onAutofix: () => void;
}

export function PlanRunView({
  run, polling, busy, selfCheck, validation, compileResult,
  onSelfCheck, onValidate, onCompile, onOpenArtifact,
  repairOutput, canRepair, onExplain, onApplyFix, onAutofix,
}: Props) {
  const [pickedArcId, setPickedArcId] = useState('');
  // PS-6 — a paid repair action confirms before spending; one confirm at a time.
  const [pendingRepair, setPendingRepair] = useState<null | { label: string; run: () => void }>(null);
  // Derived default (same pattern as PlannerPanel's effectiveModelRef) — no
  // effect needed to "sync" the picker once arcs load, since this recomputes
  // on every render from the current props instead of chasing a prop change.
  const arcId = pickedArcId || run.arcs[0]?.id || '';

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
              <li key={a.artifact_id}>
                {/* PS-9 — each row opens the artifact read-only (was a dead <li> — the body of the
                    plan the user paid an LLM to write was unreachable by any client). */}
                <button
                  type="button" data-testid={`plan-artifact-${a.kind}`}
                  onClick={() => onOpenArtifact(a.artifact_id)}
                  className="flex w-full items-center justify-between gap-2 rounded bg-muted/40 px-2 py-0.5 text-left hover:bg-muted"
                >
                  <span>{a.kind}</span>
                  <span className="font-mono text-[10px] text-accent-foreground underline">open ↗</span>
                </button>
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

      {/* ⑨ Repair strip — only when self-check surfaced gaps. All three actions are PAID. */}
      {selfCheck && selfCheck.gaps.length > 0 && (
        <div data-testid="plan-repair-strip" className="rounded border border-warning/40 bg-warning/5 p-2">
          <p className="mb-1.5 text-[10px] uppercase text-warning">
            Self-check found {selfCheck.gaps.length} gap(s) — repair
          </p>
          {pendingRepair ? (
            <div data-testid="plan-repair-confirm" className="flex items-center gap-2 text-[11px]">
              <span className="text-muted-foreground">{pendingRepair.label} · spends 1 LLM call</span>
              <button
                type="button" data-testid="plan-repair-confirm-btn"
                onClick={() => { pendingRepair.run(); setPendingRepair(null); }}
                className="ml-auto rounded bg-primary px-2 py-1 font-medium text-primary-foreground hover:brightness-110"
              >Confirm</button>
              <button type="button" onClick={() => setPendingRepair(null)}
                className="rounded border border-border px-2 py-1 hover:bg-secondary">Cancel</button>
            </div>
          ) : (
            <div className="flex flex-wrap gap-2">
              <button
                type="button" data-testid="plan-repair-explain" disabled={!canRepair}
                onClick={() => setPendingRepair({ label: 'Explain what’s wrong', run: onExplain })}
                className="rounded border border-border px-2 py-1 text-[11px] hover:bg-secondary disabled:opacity-40"
              >Explain what’s wrong</button>
              <button
                type="button" data-testid="plan-repair-apply" disabled={!canRepair}
                onClick={() => setPendingRepair({ label: 'Apply the suggested fix', run: onApplyFix })}
                className="rounded border border-border px-2 py-1 text-[11px] hover:bg-secondary disabled:opacity-40"
              >Apply the suggested fix</button>
              <button
                type="button" data-testid="plan-repair-autofix" disabled={!canRepair}
                onClick={() => setPendingRepair({ label: 'Fix the top gaps automatically', run: onAutofix })}
                className="rounded bg-primary px-2 py-1 text-[11px] font-medium text-primary-foreground hover:brightness-110 disabled:opacity-40"
              >Fix the top gaps automatically</button>
            </div>
          )}
          {repairOutput && (
            <p data-testid="plan-repair-output" className="mt-1.5 rounded bg-muted/40 px-2 py-1 text-[10px] text-muted-foreground">
              {repairOutput}
            </p>
          )}
          {!canRepair && !pendingRepair && (
            <p className="mt-1 text-[10px] text-muted-foreground/70">Choose a chat model above to enable repair.</p>
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
        {run.arcs.length === 0 ? (
          <p data-testid="plan-arc-none" className="text-muted-foreground">
            No arcs found in this plan yet — run Self-check or Validate above to see what's missing.
          </p>
        ) : (
          <div className="flex gap-2">
            <select
              data-testid="plan-arc-picker" value={arcId} onChange={(e) => setPickedArcId(e.target.value)}
              className="flex-1 rounded border border-border bg-background px-1.5 py-1 text-xs outline-none focus:border-ring"
            >
              {run.arcs.map((a) => (
                <option key={a.id} value={a.id}>{a.title}</option>
              ))}
            </select>
            <button
              type="button" data-testid="plan-compile-btn" onClick={() => onCompile(arcId)}
              disabled={busy || polling || !arcId}
              className="rounded bg-primary px-2 py-1 text-primary-foreground hover:brightness-110 disabled:opacity-40"
            >Compile</button>
          </div>
        )}
        {compileResult && (
          <p data-testid="plan-compile-result" className="text-[10px] text-muted-foreground">
            work {compileResult.work_id.slice(0, 8)}
            {compileResult.pipeline_job_id
              ? ` · pipeline ${compileResult.pipeline_job_id.slice(0, 8)}`
              : ' · package compiled (no pipeline run requested)'}
          </p>
        )}
      </div>
    </div>
  );
}
