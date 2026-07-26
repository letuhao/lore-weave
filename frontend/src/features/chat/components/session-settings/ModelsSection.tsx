// Session settings → Models. Chat / composer / planner, each showing the tier it
// resolved from, so "you picked this here" reads differently from "inherited from your
// account default" — and a picker left alone is never mistaken for a choice.
import { useTranslation } from 'react-i18next';
import { ModelPicker } from '@/components/model-picker';
import { CHAT_CAPABILITY } from '@/features/settings/api';
import { TierChip } from '@/features/chat-ai-settings/components/TierChip';
import type { SessionSettingsEditor } from '@/features/chat-ai-settings/hooks/useSessionSettingsEditor';

export function ModelsSection({ ed }: { ed: SessionSettingsEditor }) {
  const { t } = useTranslation('chat');
  const { session, effective } = ed;
  const tier = (role: string) => effective?.models?.[role]?.source_tier;

  return (
    <section className="space-y-4" data-testid="session-models-section">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Models</h4>

      <div>
        <label className="mb-1.5 flex items-center text-xs font-medium text-muted-foreground">
          {t('settings.model')}
          <TierChip tier={tier('chat')} />
        </label>
        <ModelPicker
          capability={CHAT_CAPABILITY}
          value={session.model_ref || null}
          onChange={(id) => { if (id) ed.patch({ model_source: 'user_model', model_ref: id }); }}
          ariaLabel={t('settings.model')}
        />
      </div>

      <div>
        <label className="mb-1.5 flex items-center text-xs font-medium text-muted-foreground">
          {t('settings.composer_model', { defaultValue: 'Composer model (optional)' })}
          <TierChip tier={tier('composer')} />
        </label>
        <ModelPicker
          capability={CHAT_CAPABILITY}
          value={session.composer_model_ref || null}
          // An explicit null clears the override (model_fields_set sees it) — `undefined`
          // would be dropped by JSON.stringify and read as "leave alone".
          onChange={(id) => ed.patch({
            composer_model_source: id ? 'user_model' : null,
            composer_model_ref: id ?? null,
          })}
          allowNone
          noneLabel={t('settings.composer_none', { defaultValue: 'None — single model' })}
          ariaLabel={t('settings.composer_model', { defaultValue: 'Composer model (optional)' })}
        />
        <p className="mt-1 text-[10px] text-muted-foreground">
          {t('settings.composer_hint', { defaultValue: 'When set, the AI can delegate prose-writing to this model via compose_prose (best: a reasoning model for writing + a tool-capable main model).' })}
        </p>
      </div>

      <div>
        <label className="mb-1.5 flex items-center text-xs font-medium text-muted-foreground">
          {t('settings.planner_model', { defaultValue: 'Planner model (optional)' })}
          <TierChip tier={tier('planner')} />
        </label>
        <ModelPicker
          capability={CHAT_CAPABILITY}
          value={session.planner_model_ref || null}
          onChange={(id) => ed.patch({
            planner_model_source: id ? 'user_model' : null,
            planner_model_ref: id ?? null,
          })}
          allowNone
          noneLabel={t('settings.planner_none', { defaultValue: 'Use my default planner' })}
          ariaLabel={t('settings.planner_model', { defaultValue: 'Planner model (optional)' })}
        />
        <p className="mt-1 text-[10px] text-muted-foreground">
          {t('settings.planner_hint', { defaultValue: 'The model the glossary assistant plans multi-step ontology changes with (overrides your Settings default for this session). Pick a strong, tool-capable model.' })}
        </p>
      </div>
    </section>
  );
}
