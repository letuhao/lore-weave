// Session settings → Grounding & Memory.
//
// `grounding_enabled` is the spec's silent-fallback #1: grounding was ALWAYS ON with no
// toggle anywhere (`stream_service` forced `EntityPresence(True, "gate_disabled")`), and
// only a process-global env flag governed it. The account tier got a toggle in M3; this
// is the per-chat one — and until the session column became writable it could not exist.
import { useTranslation } from 'react-i18next';
import { MultiProjectPicker } from '@/components/shared/MultiProjectPicker';
import { TierChip, ClearOverride } from '@/features/chat-ai-settings/components/TierChip';
import type { SessionSettingsEditor } from '@/features/chat-ai-settings/hooks/useSessionSettingsEditor';

export function GroundingSection({ ed }: { ed: SessionSettingsEditor }) {
  const { t: tKnowledge } = useTranslation('knowledge');
  const { t } = useTranslation('chat');
  const { session } = ed;

  const groundingField = ed.field('grounding', 'grounding_enabled');
  const on = groundingField?.effective_value !== false;
  const projectIds = session.project_ids?.length
    ? session.project_ids
    : session.project_id
      ? [session.project_id]
      : [];

  return (
    <section className="space-y-4" data-testid="session-grounding-section">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {t('sessionSettings.grounding.title')}
      </h4>

      <div>
        <label className="mb-1.5 flex items-center text-xs font-medium text-muted-foreground">
          {t('sessionSettings.grounding.label')}
          <TierChip tier={groundingField?.source_tier} />
          <ClearOverride
            show={ed.isOverridden('grounding', 'grounding_enabled')}
            inherited={ed.inheritedValue('grounding', 'grounding_enabled')}
            onClear={() => ed.patch({ grounding_enabled: null })}
            testId="session-grounding-clear"
          />
        </label>
        <button
          type="button"
          role="switch"
          aria-checked={on}
          data-testid="session-grounding-toggle"
          onClick={() => ed.patch({ grounding_enabled: !on })}
          className={`w-full rounded border px-2 py-1.5 text-[11px] font-medium transition-colors ${
            on
              ? 'border-primary bg-primary text-primary-foreground'
              : 'border-border bg-background text-muted-foreground hover:text-foreground'
          }`}
        >
          {on ? t('sessionSettings.grounding.on') : t('sessionSettings.grounding.off')}
        </button>
        <p className="mt-1 text-[10px] text-muted-foreground">
          {on
            ? t('sessionSettings.grounding.onHint')
            : t('sessionSettings.grounding.offHint')}
        </p>
      </div>

      <div>
        <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
          {tKnowledge('picker.label')}
        </label>
        {/* The grounding SET is a session concept — it never cascades, so no tier chip. */}
        <MultiProjectPicker
          value={projectIds}
          onChange={(next) => ed.patch({ project_ids: next, project_id: next[0] ?? null })}
          placeholder={tKnowledge('picker.noProject')}
        />
        <p className="mt-1 text-[10px] text-muted-foreground">
          {projectIds.length >= 2
            ? t('sessionSettings.grounding.multiHint')
            : tKnowledge('picker.hint')}
        </p>
      </div>
    </section>
  );
}
