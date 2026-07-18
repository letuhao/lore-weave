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
        Grounding &amp; memory
      </h4>

      <div>
        <label className="mb-1.5 flex items-center text-xs font-medium text-muted-foreground">
          Ground answers in this book&apos;s lore
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
          {on ? 'On — retrieval runs each turn' : 'Off — no retrieval this chat'}
        </button>
        <p className="mt-1 text-[10px] text-muted-foreground">
          {on
            ? 'Glossary, knowledge-graph facts and passages are pulled into every turn.'
            : 'The assistant answers from the conversation alone, and may invent lore.'}
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
            ? 'Grounded on every selected knowledge graph at once — facts are tagged with their source.'
            : tKnowledge('picker.hint')}
        </p>
      </div>
    </section>
  );
}
