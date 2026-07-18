// PlanForge S3 — the "Pass Rail" (`plan-passes`) dock panel. The 7-pass compiler
// (motifs → cast → world → beats → character_arcs → scenes → self_heal) exposed so a
// GUI-only author can run each pass, watch freshness/cursor/blocked_at, and approve the
// two BLOCKING checkpoints (cast = "who the characters are", beats = "what shape the story
// takes"). Before this, the passes were reachable ONLY via MCP tool-calls / raw REST.
//
// MVC: this is the view; usePassRail owns the ledger + run/checkpoint logic. Stays MOUNTED
// (never a ternary unmount — the repo FE rule).
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { IDockviewPanelProps } from 'dockview-react';
import { useAuth } from '@/auth';
import { isChatSafeDefault } from '@/features/ai-models/api';
import { ModelPicker, useUserModels } from '@/components/model-picker';
import { useStudioHost, useRegisterStudioTool } from '@/features/studio/host/StudioHostProvider';
import type { StudioToolRegistration } from '@/features/studio/host/types';
import { usePassRail } from '../hooks/usePassRail';
import { PassRow } from './PassRow';
import { CheckpointReview } from './CheckpointReview';
import { registerPlanArtifactDocumentProvider, PLAN_ARTIFACT_DOC_TYPE } from '../documents/planArtifactDocument';

export function PassRailPanel(props: IDockviewPanelProps) {
  const { t } = useTranslation('studio');
  const { bookId, openPanel } = useStudioHost();
  const { accessToken } = useAuth();
  const rail = usePassRail(bookId, accessToken ?? null);

  // Cost-confirm (PS-6): running a pass is a paid Tier-A action, so it opens a confirm with an
  // explicit model choice before spending. Only one pass's confirm is open at a time.
  const [confirmPass, setConfirmPass] = useState<string | null>(null);
  const [batchConfirm, setBatchConfirm] = useState(false); // H2 — "run to next checkpoint" cost-confirm
  const models = useUserModels({ capability: 'chat', enabled: !!confirmPass || batchConfirm });
  const [modelRef, setModelRef] = useState('');
  const autoModelRef = useMemo(() => {
    const candidates = (models.models ?? []).filter(isChatSafeDefault);
    if (!candidates.length) return '';
    return (candidates.find((m) => m.is_favorite) ?? candidates[0]).user_model_id;
  }, [models.models]);
  const effectiveModelRef = modelRef || autoModelRef;

  const label = t('panels.plan-passes.title', { defaultValue: 'Pass Rail' });
  const registration = useMemo<StudioToolRegistration>(() => ({
    panelId: 'plan-passes',
    label,
    paletteCommand: t('palette.openPanel', { name: label, defaultValue: 'Studio: Open Pass Rail' }),
    commandId: 'studio.openPanel.plan-passes',
    description: t('panels.plan-passes.desc', {
      defaultValue: 'Compile a plan pass-by-pass and approve each checkpoint',
    }),
    mcpToolPrefixes: ['plan_'],
  }), [t, label]);
  useRegisterStudioTool(registration);
  useEffect(() => { props.api.setTitle(label); }, [props.api, label]);
  // PS-9 — register the read-only plan-artifact provider so a completed pass can open its output.
  useEffect(() => { registerPlanArtifactDocumentProvider(); }, []);
  const openArtifact = (artifactId: string) => {
    if (!rail.runId) return;
    openPanel('json-editor', {
      params: { docType: PLAN_ARTIFACT_DOC_TYPE, resourceId: `${rail.runId}:${artifactId}` },
    });
  };

  const onRun = (passId: string) => { setModelRef(''); setConfirmPass(passId); };
  const doRun = () => {
    if (!confirmPass) return;
    void rail.runPass(confirmPass, effectiveModelRef || undefined);
    setConfirmPass(null);
  };
  // The rich review (artifact view + edit) lands in M4-CP; here approve/hold/reject already work.
  const [reviewPass, setReviewPass] = useState<string | null>(null);

  const ledger = rail.ledger;

  return (
    <div data-testid="studio-plan-passes-panel" className="mx-auto flex h-full w-full min-h-0 max-w-3xl flex-col overflow-auto p-3 text-xs">
      <div className="mb-2 flex items-center gap-2">
        <h2 className="text-sm font-semibold text-foreground">{label}</h2>
        {/* H4 — a run picker, so a multi-run author isn't stuck on the latest run. */}
        {rail.runs.length > 1 && (
          <select
            data-testid="plan-passes-run-picker"
            value={rail.runId ?? ''}
            onChange={(e) => rail.setRunId(e.target.value || null)}
            className="rounded border border-border bg-background px-1 py-0.5 text-[10px] outline-none focus:border-ring"
            aria-label={t('planPasses.runPicker', { defaultValue: 'Choose a plan run' })}
          >
            {rail.runs.map((r) => (
              <option key={r.id} value={r.id}>{r.id.slice(0, 8)} · {r.status}</option>
            ))}
          </select>
        )}
        <button
          type="button" data-testid="plan-passes-open-planner" onClick={() => openPanel('planner')}
          className="ml-auto text-[11px] text-accent-foreground underline"
        >
          {t('planPasses.openPlanner', { defaultValue: '← Planner (propose / compile)' })}
        </button>
      </div>

      {rail.error && (
        <p data-testid="plan-passes-error" className="mb-2 rounded bg-destructive/10 px-2 py-1 text-destructive">
          {rail.error}
        </p>
      )}

      {!bookId ? (
        <p className="text-muted-foreground">{t('planPasses.noBook', { defaultValue: 'Open a book to compile its plan.' })}</p>
      ) : !rail.runId ? (
        <p data-testid="plan-passes-no-run" className="text-muted-foreground">
          {t('planPasses.noRun', { defaultValue: 'No plan run yet — open the Planner to propose and compile one.' })}
        </p>
      ) : !ledger ? (
        <p className="text-muted-foreground">{t('planPasses.loading', { defaultValue: 'Loading passes…' })}</p>
      ) : !ledger.compiled ? (
        <p data-testid="plan-passes-not-compiled" className="rounded bg-warning/10 px-2 py-1.5 text-warning">
          {t('planPasses.notCompiled', {
            defaultValue: 'This run has no compiled package yet. Compile it in the Planner before running passes.',
          })}
        </p>
      ) : (
        <>
          {/* H2 — one click runs the runnable advisory passes to the next checkpoint. Shown while
              there is a runnable pass and no blocking checkpoint is already waiting on the human. */}
          {(() => {
            const blockingPending = ledger.passes.some((p) => p.checkpoint === 'blocking' && p.status === 'completed' && p.decision === 'pending');
            const hasRunnable = ledger.passes.some((p) => p.status !== 'completed' && p.blockers.length === 0);
            if (!hasRunnable || blockingPending) return null;
            return (
              <div className="mb-2">
                {batchConfirm ? (
                  <div data-testid="pass-batch-confirm" className="rounded border border-accent/40 bg-accent/5 p-2">
                    <p className="mb-1 text-[11px] font-medium text-foreground">
                      {t('planPasses.batchSpends', { defaultValue: 'Runs each ready pass until the next checkpoint — spends 1 LLM call per pass.' })}
                    </p>
                    <div className="mb-2"><ModelPicker capability="chat" compact value={effectiveModelRef || null} onChange={(id) => setModelRef(id ?? '')} ariaLabel={t('planner.model', { defaultValue: 'Model' })} /></div>
                    <div className="flex gap-2">
                      <button type="button" data-testid="pass-batch-run" disabled={!effectiveModelRef}
                        onClick={() => { void rail.runToNextCheckpoint(effectiveModelRef); setBatchConfirm(false); }}
                        className="rounded bg-primary px-2 py-1 text-[11px] font-medium text-primary-foreground hover:brightness-110 disabled:opacity-40">
                        {t('planPasses.runToCheckpoint', { defaultValue: 'Run to next checkpoint' })}
                      </button>
                      <button type="button" onClick={() => setBatchConfirm(false)} className="rounded border border-border px-2 py-1 text-[11px] hover:bg-secondary">
                        {t('planPasses.cancel', { defaultValue: 'Cancel' })}
                      </button>
                    </div>
                  </div>
                ) : (
                  <button type="button" data-testid="pass-run-to-checkpoint" disabled={rail.busy || rail.polling}
                    onClick={() => { setModelRef(''); setBatchConfirm(true); }}
                    className="rounded border border-accent/50 px-2 py-1 text-[11px] font-medium text-accent-foreground hover:bg-accent/10 disabled:opacity-40">
                    {rail.running ? t('planPasses.runningPass', { defaultValue: `running ${rail.running}…`, pass: rail.running }) : t('planPasses.runToCheckpoint', { defaultValue: '▶ Run to next checkpoint' })}
                  </button>
                )}
              </div>
            );
          })()}
          <div className="flex flex-col gap-1">
            {ledger.passes.map((pass, i) => (
              <div key={pass.pass_id}>
                <PassRow
                  index={i + 1}
                  pass={pass}
                  blockedAtHere={ledger.blocked_at === pass.pass_id}
                  onRun={onRun}
                  onReview={setReviewPass}
                  onView={openArtifact}
                  disabled={rail.busy || rail.polling}
                />

                {/* PS-6 cost-confirm, inline under the pass being run */}
                {confirmPass === pass.pass_id && (
                  <div data-testid="pass-cost-confirm" className="mt-1 rounded border border-accent/40 bg-accent/5 p-2">
                    <p className="mb-1 text-[11px] font-medium text-foreground">
                      {t('planPasses.runSpends', { defaultValue: `Run ${pass.pass_id} — this spends 1 LLM call`, pass: pass.pass_id })}
                    </p>
                    <div data-testid="pass-model-picker" className="mb-2">
                      <ModelPicker
                        capability="chat" compact value={effectiveModelRef || null}
                        onChange={(id) => setModelRef(id ?? '')}
                        ariaLabel={t('planner.model', { defaultValue: 'Model' })}
                      />
                    </div>
                    <div className="flex gap-2">
                      <button
                        type="button" data-testid="pass-run-confirm" onClick={doRun}
                        disabled={!effectiveModelRef}
                        className="rounded bg-primary px-2 py-1 text-[11px] font-medium text-primary-foreground hover:brightness-110 disabled:opacity-40"
                      >
                        {t('planPasses.runNow', { defaultValue: `Run ${pass.pass_id}`, pass: pass.pass_id })}
                      </button>
                      <button
                        type="button" onClick={() => setConfirmPass(null)}
                        className="rounded border border-border px-2 py-1 text-[11px] hover:bg-secondary"
                      >
                        {t('planPasses.cancel', { defaultValue: 'Cancel' })}
                      </button>
                    </div>
                  </div>
                )}

                {/* M4-CP — the rich checkpoint review: read the artifact, edit it, clear the cast
                    seed gate (PF-7), then approve/hold. */}
                {reviewPass === pass.pass_id && rail.runId && (
                  <CheckpointReview
                    pass={pass}
                    bookId={bookId}
                    runId={rail.runId}
                    token={accessToken ?? null}
                    busy={rail.busy}
                    onReview={(approved) => {
                      void rail.reviewCheckpoint(approved, pass.pass_id);
                      setReviewPass(null);
                    }}
                    onSaveEdits={(edits) => {
                      // Hold + save the revision (approved=false) — keep the review open so the
                      // author sees the edited artifact refetch, then approves separately.
                      void rail.reviewCheckpoint(false, pass.pass_id, edits);
                    }}
                    onClose={() => setReviewPass(null)}
                  />
                )}
              </div>
            ))}
          </div>

          <div
            data-testid="plan-passes-footer"
            className="mt-3 flex items-center gap-2 border-t pt-2 text-[11px] text-muted-foreground"
          >
            <span data-testid="plan-passes-cursor" className="font-mono text-foreground">
              {t('planPasses.cursor', {
                defaultValue: `${ledger.pass_cursor} of ${ledger.passes.length}`,
                done: ledger.pass_cursor, total: ledger.passes.length,
              })}
            </span>
            {ledger.blocked_at && (
              <span>
                · {t('planPasses.blockedAt', { defaultValue: 'blocked at', })}{' '}
                <span className="font-mono text-warning">{ledger.blocked_at}</span>
              </span>
            )}
            {rail.polling && <span className="animate-pulse text-accent">· working…</span>}
            {/* §2.6 loop-connect — push the compiled plan into the book's outline (the manuscript). */}
            <button
              type="button" data-testid="plan-passes-relink" disabled={rail.busy}
              onClick={() => void rail.relink('skeleton')}
              className="ml-auto rounded border border-border px-2 py-0.5 text-[10px] hover:bg-secondary disabled:opacity-40"
            >
              {t('planPasses.linkOutline', { defaultValue: 'Link to outline →' })}
            </button>
          </div>
          {rail.relinkOutput && (
            <p data-testid="plan-passes-relink-output" className="mt-1 text-[10px] text-success">{rail.relinkOutput}</p>
          )}
        </>
      )}
    </div>
  );
}
