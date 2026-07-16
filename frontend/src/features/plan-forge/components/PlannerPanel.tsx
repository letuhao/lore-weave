// PlanForge (Writing-Studio M5) — the "Planner" dock panel. Two views (D-PLANFORGE-NO-RESUME
// follow-up, mirrors #20_agent_mode.md's Runs-list/Mission-control split): "Runs" lists every
// plan run that exists server-side for this book (so reopening the panel — or a fresh device —
// doesn't look like a run was never made, CLAUDE.md "server is the source of truth"), "Run" is
// the original propose-form-plus-readout view, now also reachable by loading a past run. Both
// views stay MOUNTED (CSS hidden, never a ternary unmount — this repo's FE rule).
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { IDockviewPanelProps } from 'dockview-react';
import { useAuth } from '@/auth';
import { isChatSafeDefault } from '@/features/ai-models/api';
import { ModelPicker, useUserModels } from '@/components/model-picker';
import { useStudioHost, useRegisterStudioTool } from '@/features/studio/host/StudioHostProvider';
import type { StudioToolRegistration } from '@/features/studio/host/types';
import { useBootstrap } from '../hooks/useBootstrap';
import { usePlanRun } from '../hooks/usePlanRun';
import type { PlanRunMode } from '../types';
import { BootstrapPanel } from './BootstrapPanel';
import { PlanRunView } from './PlanRunView';
import { PlanRunsListView } from './PlanRunsListView';
import { registerPlanArtifactDocumentProvider, PLAN_ARTIFACT_DOC_TYPE } from '../documents/planArtifactDocument';

type PlannerView = 'list' | 'run';

export function PlannerPanel(props: IDockviewPanelProps) {
  const { t } = useTranslation('studio');
  const { bookId, openPanel } = useStudioHost();
  const { accessToken } = useAuth();
  const plan = usePlanRun(bookId, accessToken ?? null);
  const bootstrap = useBootstrap(bookId, accessToken ?? null);

  const [view, setView] = useState<PlannerView>('list');
  const [markdown, setMarkdown] = useState('');
  // D-PLANFORGE-GENERAL-VALIDATE: 'rules' is a hardcoded fixture parser (built
  // for one internal POC test document, not a general markdown parser — see
  // app/engine/plan_forge/propose.py) that returns 0 arcs/characters for any
  // real story. 'llm' is the only mode that genuinely reads the pasted text.
  const [mode, setMode] = useState<PlanRunMode>('llm');
  const [modelRef, setModelRef] = useState('');

  // A bootstrap proposal is scoped to ONE run — switching runs must not leave a stale
  // proposal from the previous run showing under the newly-loaded/started one. Same
  // reasoning applies to re-compiling the SAME run with a DIFFERENT arc (see the
  // onCompile handler below — /review-impl caught the case where this was missing):
  // the package artifact changes underneath the proposal, so a stale diff from the
  // previous arc must not linger as if it described the newly-picked one.
  const openRun = (runId: string) => { void plan.loadRun(runId); bootstrap.reset(); setView('run'); };
  const startNewRun = () => { plan.resetRun(); bootstrap.reset(); setMarkdown(''); setView('run'); };

  const label = t('panels.planner.title', { defaultValue: 'Planner' });
  const registration = useMemo<StudioToolRegistration>(() => ({
    panelId: 'planner',
    label,
    paletteCommand: t('palette.openPanel', { name: label, defaultValue: 'Studio: Open Planner' }),
    commandId: 'studio.openPanel.planner',
    description: t('panels.planner.desc', { defaultValue: "Plan the novel's system" }),
    mcpToolPrefixes: ['composition_'],
  }), [t, label]);
  useRegisterStudioTool(registration);

  // PS-9 — register the read-only plan-artifact json provider so an artifact row can open in the
  // json-editor. Idempotent; mirrors the other feature providers registering on mount.
  useEffect(() => { registerPlanArtifactDocumentProvider(); }, []);
  const openArtifact = (artifactId: string) => {
    if (!plan.run) return;
    openPanel('json-editor', {
      params: { docType: PLAN_ARTIFACT_DOC_TYPE, resourceId: `${plan.run.id}:${artifactId}` },
    });
  };

  // Self-title the dock tab (openPanel sets the title before mount; an agent/palette open otherwise
  // shows the raw 'planner' id). Also keeps it correct across a locale swap. See EditorPanel.
  useEffect(() => {
    props.api.setTitle(label);
  }, [props.api, label]);

  // W5 — shared user-models fetch (replaces the bespoke plan-forge ModelPicker's own
  // effect); only fetched once the llm mode needs it. The old picker auto-selected
  // the favorite/first model when nothing was chosen — preserved here as a DERIVED
  // default (no useEffect-for-events).
  const models = useUserModels({ capability: 'chat', enabled: mode === 'llm' });
  const autoModelRef = useMemo(() => {
    // D-PLANFORGE-MODEL-AUTOPICK: `capability=chat` can still include a model
    // whose OWN capability_flags explicitly declare a different job (rerank/
    // embedding/tts) — never silently hand those to a chat call.
    const candidates = (models.models ?? []).filter(isChatSafeDefault);
    if (!candidates.length) return '';
    return (candidates.find((m) => m.is_favorite) ?? candidates[0]).user_model_id;
  }, [models.models]);
  const effectiveModelRef = modelRef || autoModelRef;

  const canPropose =
    !plan.busy && !plan.polling && markdown.trim().length > 0 && (mode === 'rules' || effectiveModelRef.length > 0);

  // Bootstrap only makes sense once a run is compiled (it reads the run's package artifact).
  const compiledRunId = plan.run?.status === 'compiled' ? plan.run.id : null;

  const onPropose = () => {
    void plan.createRun({
      source_markdown: markdown,
      mode,
      ...(mode === 'llm' ? { model_ref: effectiveModelRef } : {}),
    });
  };

  return (
    <div data-testid="studio-planner-panel" className="flex h-full min-h-0 flex-col overflow-auto p-3">
      {/* 20_agent_mode.md — Agent Mode's `agent-mode` panel is hiddenFromPalette
          (see catalog.ts comment: needs a chat-service enum change out of this
          session's scope), so it needs a non-palette entry point. An approved
          plan run is the prerequisite for a run's plan picker anyway, so the
          Planner is the natural adjacent surface to link from. */}
      <div className="mb-2 flex items-center gap-3">
        <button
          type="button"
          data-testid="planner-open-agent-mode"
          onClick={() => openPanel('agent-mode')}
          className="self-start text-[11px] text-accent-foreground underline"
        >
          {t('planner.openAgentMode', { defaultValue: 'Autonomous Agent Runs →' })}
        </button>
        {/* §2.6 loop-connected — compile happens here; the passes run in the rail. Hand off. */}
        <button
          type="button"
          data-testid="planner-open-pass-rail"
          onClick={() => openPanel('plan-passes')}
          className="self-start text-[11px] text-accent-foreground underline"
        >
          {t('planner.openPassRail', { defaultValue: 'Pass Rail →' })}
        </button>
      </div>

      <div className="mb-2 flex gap-4 border-b" role="tablist" aria-label={t('planner.list.title', { defaultValue: 'Runs for this book' })}>
        {([
          { id: 'list' as const, labelKey: 'planner.tabList', label: 'Runs' },
          { id: 'run' as const, labelKey: 'planner.tabRun', label: 'Run' },
        ]).map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={view === tab.id}
            data-testid={`plan-tab-${tab.id}`}
            onClick={() => setView(tab.id)}
            className={`border-b-2 px-1 pb-2 text-xs font-semibold ${
              view === tab.id ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            {t(tab.labelKey, { defaultValue: tab.label })}
          </button>
        ))}
      </div>

      <div data-testid="planner-view-list" className={`min-h-0 flex-1 overflow-auto ${view !== 'list' ? 'hidden' : ''}`}>
        <PlanRunsListView bookId={bookId} onOpenRun={openRun} onNewRun={startNewRun} />
      </div>

      <div data-testid="planner-view-run" className={`flex min-h-0 flex-1 flex-col ${view !== 'run' ? 'hidden' : ''}`}>
        <textarea
          data-testid="plan-source-input"
          value={markdown}
          onChange={(e) => setMarkdown(e.target.value)}
          placeholder={t('planner.sourcePlaceholder', { defaultValue: 'Paste the novel-system markdown…' })}
          className="min-h-[120px] w-full resize-y rounded border border-border bg-background p-2 text-xs leading-relaxed outline-none focus:border-ring"
        />
        {/* D-PLANFORGE-PROPOSE-BLIND honesty (Q-35-OQ5): the proposer reads ONLY this braindump —
            it does not read the book's existing chapters. Say so, rather than let the author assume
            an in-context plan (silent-success-is-a-bug applied to a known blindness). */}
        <p data-testid="plan-propose-blind-note" className="mt-1 text-[10px] text-muted-foreground/70">
          {t('planner.proposeBlind', { defaultValue: 'Proposed from this braindump only. Existing chapters are not read.' })}
        </p>

        <div className="mt-2 flex items-end gap-3">
          <div className="flex gap-1 text-[11px]">
            {(['rules', 'llm'] as const).map((m) => (
              <button
                key={m}
                type="button"
                data-testid={`plan-mode-${m}`}
                onClick={() => setMode(m)}
                className={`rounded border px-2 py-1 ${
                  mode === m ? 'border-accent bg-accent/10 text-foreground' : 'border-border text-muted-foreground hover:bg-secondary'
                }`}
              >
                {t(`planner.mode.${m}`, { defaultValue: m })}
              </button>
            ))}
          </div>
          {mode === 'llm' && (
            <div className="flex-1 text-[11px] text-muted-foreground">
              <span className="block">{t('planner.model', { defaultValue: 'Model' })}</span>
              <div data-testid="plan-model-picker" className="mt-1">
                <ModelPicker
                  capability="chat"
                  compact
                  value={effectiveModelRef || null}
                  onChange={(id) => setModelRef(id ?? '')}
                  ariaLabel={t('planner.model', { defaultValue: 'Model' })}
                />
              </div>
            </div>
          )}
          <button
            type="button"
            data-testid="plan-propose-btn"
            onClick={onPropose}
            disabled={!canPropose}
            className="ml-auto rounded bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:brightness-110 disabled:opacity-40"
          >
            {t('planner.propose', { defaultValue: 'Propose' })}
          </button>
        </div>

        {plan.error && (
          <p data-testid="plan-error" className="mt-2 rounded bg-destructive/10 px-2 py-1 text-xs text-destructive">
            {plan.error}
          </p>
        )}

        <div className="mt-3 min-h-0 flex-1 overflow-auto">
          {plan.run ? (
            <>
              <PlanRunView
                run={plan.run}
                polling={plan.polling}
                busy={plan.busy}
                selfCheck={plan.selfCheck}
                validation={plan.validation}
                compileResult={plan.compileResult}
                onSelfCheck={() => void plan.runSelfCheck()}
                onValidate={() => void plan.runValidate()}
                onCompile={(arcId) => { bootstrap.reset(); void plan.runCompile(arcId); }}
                onOpenArtifact={openArtifact}
                repairOutput={plan.repairOutput}
                canRepair={!plan.busy && !plan.polling && effectiveModelRef.length > 0}
                onExplain={() => void plan.runExplain(effectiveModelRef)}
                onApplyFix={() => void plan.runRepairRefine(effectiveModelRef, (plan.selfCheck?.gaps ?? []).map((g) => g.path))}
                onAutofix={() => void plan.runAutofix(effectiveModelRef)}
              />
              {compiledRunId && (
                <BootstrapPanel
                  proposal={bootstrap.proposal}
                  busy={bootstrap.busy}
                  error={bootstrap.error}
                  onPropose={() => void bootstrap.propose(compiledRunId)}
                  onApprove={() => void bootstrap.approve()}
                  onReject={() => void bootstrap.reject()}
                  onApply={() => void bootstrap.apply()}
                />
              )}
            </>
          ) : (
            <p className="text-center text-xs text-muted-foreground">
              {t('planner.empty', { defaultValue: 'Paste your novel-system markdown and Propose to start a plan run.' })}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
