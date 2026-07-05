// PlanForge (Writing-Studio M5) — the "Planner" dock panel. A thin view over usePlanRun: a
// source-markdown textarea + rules/llm toggle + a model picker (required for llm) → Propose, then
// the run read-out (status · artifacts · self-check · validate · compile). Self-titles its dock tab
// + registers for the agent rack, mirroring EditorPanel/ComposePanel.
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { IDockviewPanelProps } from 'dockview-react';
import { useAuth } from '@/auth';
import { ModelPicker, useUserModels } from '@/components/model-picker';
import { useStudioHost, useRegisterStudioTool } from '@/features/studio/host/StudioHostProvider';
import type { StudioToolRegistration } from '@/features/studio/host/types';
import { usePlanRun } from '../hooks/usePlanRun';
import type { PlanRunMode } from '../types';
import { PlanRunView } from './PlanRunView';

export function PlannerPanel(props: IDockviewPanelProps) {
  const { t } = useTranslation('studio');
  const { bookId, openPanel } = useStudioHost();
  const { accessToken } = useAuth();
  const plan = usePlanRun(bookId, accessToken ?? null);

  const [markdown, setMarkdown] = useState('');
  const [mode, setMode] = useState<PlanRunMode>('rules');
  const [modelRef, setModelRef] = useState('');

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
    if (!models.models?.length) return '';
    return (models.models.find((m) => m.is_favorite) ?? models.models[0]).user_model_id;
  }, [models.models]);
  const effectiveModelRef = modelRef || autoModelRef;

  const canPropose =
    !plan.busy && !plan.polling && markdown.trim().length > 0 && (mode === 'rules' || effectiveModelRef.length > 0);

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
      <button
        type="button"
        data-testid="planner-open-agent-mode"
        onClick={() => openPanel('agent-mode')}
        className="mb-2 self-start text-[11px] text-accent-foreground underline"
      >
        {t('planner.openAgentMode', { defaultValue: 'Autonomous Agent Runs →' })}
      </button>
      <textarea
        data-testid="plan-source-input"
        value={markdown}
        onChange={(e) => setMarkdown(e.target.value)}
        placeholder={t('planner.sourcePlaceholder', { defaultValue: 'Paste the novel-system markdown…' })}
        className="min-h-[120px] w-full resize-y rounded border border-border bg-background p-2 text-xs leading-relaxed outline-none focus:border-ring"
      />

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

      <div className="mt-3 min-h-0 flex-1">
        {plan.run ? (
          <PlanRunView
            run={plan.run}
            polling={plan.polling}
            busy={plan.busy}
            selfCheck={plan.selfCheck}
            validation={plan.validation}
            compileResult={plan.compileResult}
            onSelfCheck={() => void plan.runSelfCheck()}
            onValidate={() => void plan.runValidate()}
            onCompile={(arcId) => void plan.runCompile(arcId)}
          />
        ) : (
          <p className="text-center text-xs text-muted-foreground">
            {t('planner.empty', { defaultValue: 'Paste your novel-system markdown and Propose to start a plan run.' })}
          </p>
        )}
      </div>
    </div>
  );
}
