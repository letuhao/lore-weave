// Session settings → {t('sessionSettings.context.title')} (spec §5, G5).
//
// `mode` was a process-global env flag reshaping every turn invisibly. It became an
// account setting in M5; this is the per-chat override. Note the precedence the spec
// locks in: the env flags remain a deploy-time CEILING/kill-switch — `effective =
// AND(deploy, cascade)`. Choosing "on" here cannot switch on a tier the deployment
// forbids, and the backend says so rather than silently ignoring the choice.
import { TierChip, ClearOverride } from '@/features/chat-ai-settings/components/TierChip';
import { useTranslation } from 'react-i18next';
import type { SessionSettingsEditor } from '@/features/chat-ai-settings/hooks/useSessionSettingsEditor';

const MODES = [
  { key: 'auto' },
  { key: 'on' },
  { key: 'off' },
] as const;

const SEG = 'flex-1 rounded border px-2 py-1 text-[11px] font-medium transition-colors';
const SEG_ON = 'border-primary bg-primary text-primary-foreground';
const SEG_OFF = 'border-border bg-background text-muted-foreground hover:text-foreground';

export function ContextSection({ ed }: { ed: SessionSettingsEditor }) {
  const { t } = useTranslation('chat');
  const modeField = ed.field('context', 'mode');
  const mode = String(modeField?.effective_value ?? 'auto');

  return (
    <section className="space-y-3" data-testid="session-context-section">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {t('sessionSettings.context.title')}
      </h4>

      <label className="flex items-center text-xs font-medium text-muted-foreground">
        {t('sessionSettings.context.label')}
        <TierChip tier={modeField?.source_tier} />
        <ClearOverride
          show={ed.isOverridden('context', 'mode')}
          inherited={ed.inheritedValue('context', 'mode')}
          onClear={() => ed.patch({ context_overrides: { mode: null } })}
          testId="session-context-mode-clear"
        />
      </label>

      <div className="flex gap-1" role="group" aria-label={t('sessionSettings.context.label')}>
        {MODES.map((m) => (
          <button
            key={m.key}
            type="button"
            data-testid={`session-context-mode-${m.key}`}
            aria-pressed={mode === m.key}
            onClick={() => ed.patch({ context_overrides: { mode: m.key } })}
            className={`${SEG} ${mode === m.key ? SEG_ON : SEG_OFF}`}
          >
            {t('sessionSettings.context.' + m.key)}
          </button>
        ))}
      </div>

      <p className="text-[10px] text-muted-foreground">
        {t('sessionSettings.context.' + mode + 'Hint')}
      </p>
    </section>
  );
}
