// Chat & AI settings — the consolidated account-level panel (MVC "view": render
// only; logic in useAiPrefsEditor). Folds the fragmented model + behavior
// settings into one surface built on the resolution cascade (spec §8): every row
// shows its effective value AND which tier supplied it, so nothing is silent.
import { DefaultModelsCard } from '@/features/settings/DefaultModelsCard';
import { ModelPicker } from '@/components/model-picker';
import { useAiPrefsEditor } from '../hooks/useAiPrefsEditor';
import { TierChip } from './TierChip';
import type { EffectiveSettings, FieldResolution } from '../types';

const MODEL_ROLES: { key: string; label: string }[] = [
  { key: 'chat', label: 'Chat & drafting' },
  { key: 'composer', label: 'Prose composer' },
  { key: 'planner', label: 'Planner' },
  { key: 'embedding', label: 'Embedding' },
  { key: 'rerank', label: 'Rerank' },
];

/** The tier chip is shared with the SESSION panel (`./TierChip`) — one chip, one
 *  vocabulary. A second local copy is how "account" and "your default" drift apart. */
const SourceChip = TierChip;

function effField(eff: EffectiveSettings | null, cat: 'behavior', field: string): FieldResolution | undefined {
  return eff?.[cat]?.[field];
}

const SEG = 'rounded border text-xs font-medium px-2.5 py-1';
const SEG_ON = 'bg-primary text-primary-foreground border-primary';
const SEG_OFF = 'bg-background text-muted-foreground border-border hover:text-foreground';

export function ChatAiSettingsPanel() {
  const ed = useAiPrefsEditor();
  const behavior = ed.prefs?.behavior ?? {};
  const eff = ed.effective;

  const setBehavior = (field: string, value: unknown) =>
    void ed.patch({ behavior: { [field]: value } });

  const reasoning = String(effField(eff, 'behavior', 'reasoning_effort')?.effective_value ?? 'off');
  const permission = String(effField(eff, 'behavior', 'permission_mode')?.effective_value ?? 'write');
  const groundingOn = eff?.grounding?.grounding_enabled?.effective_value !== false;
  const groundingTier = eff?.grounding?.grounding_enabled?.source_tier;
  const contextMode = String(eff?.context?.mode?.effective_value ?? 'auto');
  const contextTier = eff?.context?.mode?.source_tier;
  const voiceBlob = (ed.prefs?.voice ?? {}) as {
    chat?: { tts_model_ref?: string; tts_voice_id?: string; tts_source?: string };
    stt?: { model_ref?: string; source?: string };
  };
  const voiceChat = voiceBlob.chat ?? {};
  const voiceStt = voiceBlob.stt ?? {};

  return (
    <div className="flex flex-col gap-8" data-testid="chat-ai-settings">
      <header>
        <h2 className="font-serif text-lg font-semibold">Chat &amp; AI</h2>
        <p className="mt-1 max-w-[64ch] text-[13px] text-muted-foreground">
          Your defaults for chat and the Writing Studio, in one place. Each row shows its
          effective value and which tier it comes from — a chat session or a Studio tool inherits
          these and may override, never required.
        </p>
        {ed.error && <p className="mt-2 text-xs text-amber-700">{ed.error}</p>}
      </header>

      {/* ── Models ── */}
      <section className="flex flex-col gap-3">
        <h3 className="font-serif text-base font-semibold">Models</h3>
        <div className="rounded-lg border border-border bg-card p-3">
          <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
            Resolved now
          </p>
          <ul className="flex flex-col gap-1.5">
            {MODEL_ROLES.map((r) => {
              const m = eff?.models?.[r.key];
              const name = m?.effective_value?.model_ref ?? null;
              return (
                <li key={r.key} className="flex items-center justify-between text-[13px]">
                  <span className="text-muted-foreground">{r.label}</span>
                  <span className="flex items-center">
                    <span className="font-mono text-xs">{name ? name.slice(0, 8) : '—'}</span>
                    <SourceChip tier={m?.source_tier} />
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
        {/* the account-default editor (shared with Providers), embedded here so
            models are set in the same place they're consumed. */}
        <DefaultModelsCard />
      </section>

      {/* ── Behavior (de-silenced defaults) ── */}
      <section className="flex flex-col gap-4">
        <h3 className="font-serif text-base font-semibold">Behavior</h3>
        <p className="-mt-2 max-w-[64ch] text-[12px] text-muted-foreground">
          These were applied silently before — now they're shown and editable. Blank means the
          system default (also shown), never a hidden value.
        </p>

        <div className="flex flex-col gap-1.5" role="group" aria-label="Reasoning effort">
          <span className="flex items-center text-[13px] font-medium">
            Reasoning effort <SourceChip tier={effField(eff, 'behavior', 'reasoning_effort')?.source_tier} />
          </span>
          <span className="flex gap-1.5">
            {(['off', 'low', 'medium', 'high'] as const).map((v) => (
              <button key={v} type="button" disabled={ed.saving}
                className={`${SEG} ${reasoning === v ? SEG_ON : SEG_OFF}`}
                onClick={() => setBehavior('reasoning_effort', v)}>
                {v}
              </button>
            ))}
          </span>
        </div>

        <div className="flex flex-col gap-1.5" role="group" aria-label="Tool authority">
          <span className="flex items-center text-[13px] font-medium">
            Tool authority <SourceChip tier={effField(eff, 'behavior', 'permission_mode')?.source_tier} />
          </span>
          <span className="flex gap-1.5">
            {(['ask', 'plan', 'write'] as const).map((v) => (
              <button key={v} type="button" disabled={ed.saving}
                className={`${SEG} ${permission === v ? SEG_ON : SEG_OFF}`}
                onClick={() => setBehavior('permission_mode', v)}>
                {v}
              </button>
            ))}
          </span>
          <span className="text-[11px] text-muted-foreground">How much the assistant may do without asking. Default granted <b>write</b> silently.</span>
        </div>

        <label className="flex flex-col gap-1.5">
          <span className="flex items-center text-[13px] font-medium">
            Temperature <SourceChip tier={effField(eff, 'behavior', 'temperature')?.source_tier} />
          </span>
          <input
            type="number" min={0} max={2} step={0.05} disabled={ed.saving}
            className="w-28 rounded border border-border bg-background px-2 py-1 text-sm"
            placeholder="provider default"
            value={behavior.temperature != null ? String(behavior.temperature) : ''}
            onChange={(e) => setBehavior('temperature', e.target.value === '' ? null : Number(e.target.value))}
          />
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="flex items-center text-[13px] font-medium">
            System prompt <SourceChip tier={effField(eff, 'behavior', 'system_prompt')?.source_tier} />
          </span>
          <textarea
            rows={3} disabled={ed.saving}
            className="rounded border border-border bg-background px-2 py-1.5 text-sm"
            placeholder="Default persona instructions (blank = none)"
            defaultValue={typeof behavior.system_prompt === 'string' ? behavior.system_prompt : ''}
            onBlur={(e) => {
              const v = e.target.value.trim();
              setBehavior('system_prompt', v === '' ? null : v);
            }}
          />
        </label>
      </section>

      {/* ── Grounding & Memory (the biggest hidden default) ── */}
      <section className="flex flex-col gap-3">
        <h3 className="font-serif text-base font-semibold">Grounding &amp; Memory</h3>
        <div className="flex items-start justify-between gap-4">
          <div className="max-w-[52ch]">
            <span className="flex items-center text-[13px] font-medium">
              Ground answers in my story <SourceChip tier={groundingTier} />
            </span>
            <p className="mt-0.5 text-[12px] text-muted-foreground">
              Pull canonical entities, facts, and manuscript passages into each answer. This was
              always on with no way to turn it off — now it's a real switch (recommended on).
            </p>
          </div>
          <button
            type="button" role="switch" aria-checked={groundingOn} aria-label="Ground answers in my story"
            disabled={ed.saving}
            onClick={() => void ed.patch({ grounding: { grounding_enabled: !groundingOn } })}
            className={`mt-1 h-6 w-11 flex-none rounded-full border transition-colors ${groundingOn ? 'bg-primary border-primary' : 'bg-muted border-border'}`}
          >
            <span className={`block h-5 w-5 rounded-full bg-white shadow transition-transform ${groundingOn ? 'translate-x-5' : 'translate-x-0.5'}`} />
          </button>
        </div>
        {!groundingOn && (
          <p className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-[12px] text-amber-800">
            Grounding is off — the assistant has no access to your story bible and may invent lore as
            fact. Turn it back on for accurate, grounded answers.
          </p>
        )}
      </section>

      {/* ── Context management (advanced; for very large works) ── */}
      <section className="flex flex-col gap-3">
        <h3 className="font-serif text-base font-semibold">Context management</h3>
        <p className="-mt-1 max-w-[64ch] text-[12px] text-muted-foreground">
          How the assistant manages a very long conversation's memory budget. It matters only on very
          large works (thousands of chapters); most people leave it on <b>Auto</b>.
        </p>
        <div className="flex flex-col gap-1.5" role="group" aria-label="Long-work context mode">
          <span className="flex items-center text-[13px] font-medium">
            Long-work context mode <SourceChip tier={contextTier} />
          </span>
          <span className="flex gap-1.5">
            {(['auto', 'on', 'off'] as const).map((v) => (
              <button key={v} type="button" disabled={ed.saving}
                className={`${SEG} ${contextMode === v ? SEG_ON : SEG_OFF}`}
                onClick={() => void ed.patch({ context: { mode: v } })}>
                {v === 'auto' ? 'Auto' : v === 'on' ? 'Always on' : 'Off'}
              </button>
            ))}
          </span>
          <span className="text-[11px] text-muted-foreground">
            Auto engages the long-work tiers only when a project is big enough to need them. Off keeps
            the simple path (recommended unless you work on a thousand-chapter novel).
          </span>
        </div>
      </section>

      {/* ── Voice (unified home; was split across two disconnected stores) ── */}
      <section className="flex flex-col gap-3">
        <h3 className="font-serif text-base font-semibold">Voice</h3>
        <p className="-mt-1 max-w-[64ch] text-[12px] text-muted-foreground">
          Speech-in and speech-out for chat. Saved here (server-side) and applied to every voice
          message — no longer resets between calls.
        </p>

        <div className="flex flex-col gap-1.5">
          <span className="text-[13px] font-medium">Speech-out model (TTS)</span>
          <ModelPicker
            capability="tts"
            value={voiceChat.tts_model_ref ?? null}
            // 'ai_model' (not 'user_model') — the audio SOURCE axis, not the model-source axis.
            // The voice store has always used this word; the bridge normalizes the old one.
            onChange={(id) => void ed.patch({ voice: { chat: { tts_model_ref: id, tts_source: 'ai_model' } } })}
            allowNone
            ariaLabel="Speech-out model"
          />
        </div>

        <label className="flex flex-col gap-1.5">
          <span className="text-[13px] font-medium">Voice</span>
          <input
            type="text" disabled={ed.saving}
            className="w-56 rounded border border-border bg-background px-2 py-1 text-sm"
            placeholder="e.g. af_heart"
            defaultValue={voiceChat.tts_voice_id ?? ''}
            onBlur={(e) => {
              const v = e.target.value.trim();
              void ed.patch({ voice: { chat: { tts_voice_id: v === '' ? null : v } } });
            }}
          />
          <span className="text-[11px] text-muted-foreground">A voice is specific to its model — pick a voice your TTS model supports.</span>
        </label>

        <div className="flex flex-col gap-1.5">
          <span className="text-[13px] font-medium">Speech-in model (STT)</span>
          <ModelPicker
            capability="stt"
            value={voiceStt.model_ref ?? null}
            onChange={(id) => void ed.patch({ voice: { stt: { model_ref: id, source: 'ai_model' } } })}
            allowNone
            ariaLabel="Speech-in model"
          />
        </div>
      </section>
    </div>
  );
}
