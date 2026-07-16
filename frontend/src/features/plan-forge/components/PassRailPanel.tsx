// PlanForge S3 — the "Pass Rail" (`plan-passes`) dock panel. The 7-pass compiler
// (motifs → cast → world → beats → character_arcs → scenes → self_heal) exposed so a
// GUI-only author can run each pass, watch freshness/cursor/blocked_at, and approve the
// two BLOCKING checkpoints (cast = "who the characters are", beats = "what shape the story
// takes"). Before this, the passes were reachable ONLY via MCP tool-calls / raw REST.
//
// B0 lands the registry-visible scaffold (this file + catalog/enum/contract/i18n); M4 fills
// in the ledger + run-pass, M4-CP the checkpoint review. Stays MOUNTED (never a ternary
// unmount — the repo FE rule).
import { useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import type { IDockviewPanelProps } from 'dockview-react';
import { useStudioHost, useRegisterStudioTool } from '@/features/studio/host/StudioHostProvider';
import type { StudioToolRegistration } from '@/features/studio/host/types';

export function PassRailPanel(props: IDockviewPanelProps) {
  const { t } = useTranslation('studio');
  const { bookId } = useStudioHost();

  const label = t('panels.plan-passes.title', { defaultValue: 'Pass Rail' });
  const registration = useMemo<StudioToolRegistration>(() => ({
    panelId: 'plan-passes',
    label,
    paletteCommand: t('palette.openPanel', { name: label, defaultValue: 'Studio: Open Pass Rail' }),
    commandId: 'studio.openPanel.plan-passes',
    description: t('panels.plan-passes.desc', {
      defaultValue: 'Compile a plan pass-by-pass and approve each checkpoint',
    }),
    // Every capability on this rail is a `plan_*` MCP tool (plan_run_pass, plan_pass_status,
    // plan_review_checkpoint, plan_handoff_autofix, plan_link, plan_apply_revision).
    mcpToolPrefixes: ['plan_'],
  }), [t, label]);
  useRegisterStudioTool(registration);

  // Self-title the dock tab (an agent/palette open otherwise shows the raw id). See PlannerPanel.
  useEffect(() => {
    props.api.setTitle(label);
  }, [props.api, label]);

  return (
    <div
      data-testid="studio-plan-passes-panel"
      className="flex h-full min-h-0 flex-col overflow-auto p-3 text-xs"
    >
      <h2 className="text-sm font-semibold text-foreground">{label}</h2>
      {!bookId ? (
        <p className="mt-2 text-muted-foreground">
          {t('planPasses.noBook', { defaultValue: 'Open a book to compile its plan.' })}
        </p>
      ) : (
        <p className="mt-2 text-muted-foreground">
          {t('planPasses.comingSoon', { defaultValue: 'The 7-pass rail loads here.' })}
        </p>
      )}
    </div>
  );
}
