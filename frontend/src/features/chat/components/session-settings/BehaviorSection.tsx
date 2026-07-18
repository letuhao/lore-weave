// Session settings → Behavior. System prompt (+ the ONE preset list), reasoning effort,
// and the sampling params — each showing which tier supplied it and offering "clear ·
// inherit X" when this chat overrides it.
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { TierChip, ClearOverride } from '@/features/chat-ai-settings/components/TierChip';
import type { SessionSettingsEditor } from '@/features/chat-ai-settings/hooks/useSessionSettingsEditor';
import { PROMPT_PRESETS, CUSTOM_PRESET_KEY, presetForPrompt, promptForPreset } from '../../prompts/presets';
import type { ReasoningEffort } from '../../types';
import { OverridableSlider } from './OverridableSlider';

const EFFORTS: ReasoningEffort[] = ['off', 'low', 'medium', 'high'];
const SEG = 'flex-1 rounded border px-2 py-1 text-[11px] font-medium transition-colors';
const SEG_ON = 'border-primary bg-primary text-primary-foreground';
const SEG_OFF = 'border-border bg-background text-muted-foreground hover:text-foreground';

export function BehaviorSection({ ed }: { ed: SessionSettingsEditor }) {
  const { t } = useTranslation('chat');
  const { session } = ed;
  const [prompt, setPrompt] = useState(session.system_prompt ?? '');
  useEffect(() => { setPrompt(session.system_prompt ?? ''); }, [session.session_id]);

  const presetKey = presetForPrompt(prompt)?.key ?? CUSTOM_PRESET_KEY;
  const effort = String(ed.field('behavior', 'reasoning_effort')?.effective_value ?? 'off');
  const effortTier = ed.field('behavior', 'reasoning_effort')?.source_tier;

  const setGen = (patch: Record<string, unknown>) => ed.patch({ generation_params: patch });

  return (
    <section className="space-y-4" data-testid="session-behavior-section">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Behavior</h4>

      {/* System prompt + the one shared preset list */}
      <div>
        <div className="mb-1.5 flex items-center justify-between">
          <label className="flex items-center text-xs font-medium text-muted-foreground">
            System prompt
            {/* The chip reads the SAME override predicate as every other row — a hand-rolled
                `session.system_prompt ? 'session' : …` here would drift from `isOverridden`
                the moment either definition changed. */}
            <TierChip tier={ed.field('behavior', 'system_prompt')?.source_tier} />
            <ClearOverride
              show={ed.isOverridden('behavior', 'system_prompt')}
              inherited={ed.inheritedValue('behavior', 'system_prompt')}
              onClear={() => { setPrompt(''); ed.patch({ system_prompt: '' }); }}
              testId="session-system-prompt-clear"
            />
          </label>
          <select
            value={presetKey}
            data-testid="session-preset-select"
            onChange={(e) => {
              const next = promptForPreset(e.target.value);
              // "Custom" must never overwrite what the user typed — it only labels it.
              if (next === null) return;
              setPrompt(next);
              ed.patch({ system_prompt: next });
            }}
            className="rounded border border-border bg-background px-2 py-1 text-[11px]"
          >
            <option value={CUSTOM_PRESET_KEY}>
              {t(`presets.${CUSTOM_PRESET_KEY}`, { defaultValue: 'Custom' })}
            </option>
            {PROMPT_PRESETS.map((p) => (
              <option key={p.key} value={p.key}>
                {p.icon} {t(`presets.${p.key}`, { defaultValue: p.label })}
              </option>
            ))}
          </select>
        </div>
        <textarea
          value={prompt}
          rows={4}
          data-testid="session-system-prompt"
          onChange={(e) => { setPrompt(e.target.value); ed.patch({ system_prompt: e.target.value }); }}
          className="w-full rounded border border-border bg-background p-2 text-xs"
          placeholder="Inherited from your account default unless you set one here."
        />
      </div>

      {/* Reasoning effort — was silently 'off' with no UI (spec §1 fallback #2) */}
      <div>
        <label className="mb-1.5 flex items-center text-xs font-medium text-muted-foreground">
          Reasoning effort
          <TierChip tier={effortTier} />
          <ClearOverride
            show={ed.isOverridden('behavior', 'reasoning_effort')}
            inherited={ed.inheritedValue('behavior', 'reasoning_effort')}
            onClear={() => setGen({ reasoning_effort: null, thinking: null })}
            testId="session-effort-clear"
          />
        </label>
        <div className="flex gap-1" role="group" aria-label="Reasoning effort">
          {EFFORTS.map((e) => (
            <button
              key={e}
              type="button"
              data-testid={`session-effort-${e}`}
              aria-pressed={effort === e}
              onClick={() => setGen({ reasoning_effort: e, thinking: null })}
              className={`${SEG} ${effort === e ? SEG_ON : SEG_OFF}`}
            >
              {e}
            </button>
          ))}
        </div>
      </div>

      <OverridableSlider
        label="Temperature" testId="session-temperature"
        field={ed.field('behavior', 'temperature')}
        overridden={ed.isOverridden('behavior', 'temperature')}
        inherited={ed.inheritedValue('behavior', 'temperature')}
        min={0} max={2} step={0.1} seed={0.7}
        format={(v) => v.toFixed(1)}
        onSet={(v) => setGen({ temperature: v })}
        onClear={() => setGen({ temperature: null })}
        hint="Higher is more surprising, lower is more predictable."
      />

      <OverridableSlider
        label="Top P" testId="session-top-p"
        field={ed.field('behavior', 'top_p')}
        overridden={ed.isOverridden('behavior', 'top_p')}
        inherited={ed.inheritedValue('behavior', 'top_p')}
        min={0} max={1} step={0.05} seed={0.9}
        onSet={(v) => setGen({ top_p: v })}
        onClear={() => setGen({ top_p: null })}
      />

      <OverridableSlider
        label="Max response tokens" testId="session-max-tokens"
        field={ed.field('behavior', 'max_tokens')}
        overridden={ed.isOverridden('behavior', 'max_tokens')}
        inherited={ed.inheritedValue('behavior', 'max_tokens')}
        min={256} max={32768} step={256} seed={4096}
        format={(v) => String(Math.round(v))}
        onSet={(v) => setGen({ max_tokens: Math.round(v) })}
        onClear={() => setGen({ max_tokens: null })}
        hint="Unset means the model's own limit — the old ∞ checkbox."
      />
    </section>
  );
}
