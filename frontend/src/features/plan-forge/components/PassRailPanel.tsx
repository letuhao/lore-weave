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

export function PassRailPanel(props: IDockviewPanelProps) {
  const { t } = useTranslation('studio');
  const { bookId, openPanel } = useStudioHost();
  const { accessToken } = useAuth();
  const rail = usePassRail(bookId, accessToken ?? null);

  // Cost-confirm (PS-6): running a pass is a paid Tier-A action, so it opens a confirm with an
  // explicit model choice before spending. Only one pass's confirm is open at a time.
  const [confirmPass, setConfirmPass] = useState<string | null>(null);
  const models = useUserModels({ capability: 'chat', enabled: !!confirmPass });
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
          <div className="flex flex-col gap-1">
            {ledger.passes.map((pass, i) => (
              <div key={pass.pass_id}>
                <PassRow
                  index={i + 1}
                  pass={pass}
                  blockedAtHere={ledger.blocked_at === pass.pass_id}
                  onRun={onRun}
                  onReview={setReviewPass}
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

                {/* Basic checkpoint review (M4-CP adds artifact view + edit) */}
                {reviewPass === pass.pass_id && (
                  <div data-testid="pass-review-strip" className="mt-1 rounded border border-warning/40 bg-warning/5 p-2">
                    <p className="mb-2 text-[11px] text-foreground">
                      {t('planPasses.reviewPrompt', {
                        defaultValue: `Approve ${pass.pass_id}? This lets the compiler proceed past it.`,
                        pass: pass.pass_id,
                      })}
                    </p>
                    <div className="flex gap-2">
                      <button
                        type="button" data-testid="pass-approve" disabled={rail.busy}
                        onClick={() => { void rail.reviewCheckpoint(true, pass.pass_id); setReviewPass(null); }}
                        className="rounded bg-primary px-2 py-1 text-[11px] font-medium text-primary-foreground hover:brightness-110 disabled:opacity-40"
                      >
                        {t('planPasses.approve', { defaultValue: 'Approve' })}
                      </button>
                      <button
                        type="button" data-testid="pass-reject" disabled={rail.busy}
                        onClick={() => { void rail.reviewCheckpoint(false, pass.pass_id); setReviewPass(null); }}
                        className="rounded border border-destructive/50 px-2 py-1 text-[11px] text-destructive hover:bg-destructive/10 disabled:opacity-40"
                      >
                        {t('planPasses.reject', { defaultValue: 'Reject' })}
                      </button>
                      <button
                        type="button" onClick={() => setReviewPass(null)}
                        className="rounded border border-border px-2 py-1 text-[11px] hover:bg-secondary"
                      >
                        {t('planPasses.cancel', { defaultValue: 'Cancel' })}
                      </button>
                    </div>
                  </div>
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
          </div>
        </>
      )}
    </div>
  );
}
