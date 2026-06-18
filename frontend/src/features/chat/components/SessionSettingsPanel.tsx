import { useCallback, useEffect, useRef, useState } from 'react';
import { Settings, X, Brain, Zap } from 'lucide-react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth';
import { aiModelsApi, type UserModel } from '@/features/ai-models/api';
import { ProjectPicker } from '@/components/shared/ProjectPicker';
import { chatApi } from '../api';
import type { ChatSession, GenerationParams, PatchSessionPayload } from '../types';

const SYSTEM_PROMPT_PRESETS: Record<string, string> = {
  Custom: '',
  Novelist: 'You are a creative writing assistant specializing in novels. Analyze character arcs, plot structure, and worldbuilding with a focus on internal consistency. When suggesting changes, provide concrete scene rewrites.',
  Translator: 'You are a literary translator. Preserve the tone, style, and nuance of the original text. Explain translation choices when they involve cultural adaptation or idiomatic expressions.',
  Worldbuilder: 'You are a worldbuilding consultant for fantasy and sci-fi settings. Help create consistent magic systems, political structures, geography, and cultural details. Flag inconsistencies.',
  Editor: 'You are a professional book editor. Focus on pacing, dialogue quality, show-vs-tell, and narrative voice. Be specific and constructive in feedback.',
  Analyst: 'You are a literary analyst. Examine themes, symbolism, narrative techniques, and character psychology. Support observations with textual evidence.',
};

interface SessionSettingsPanelProps {
  session: ChatSession;
  onSessionUpdate: (updated: ChatSession) => void;
  onClose: () => void;
}

export function SessionSettingsPanel({ session, onSessionUpdate, onClose }: SessionSettingsPanelProps) {
  const { t } = useTranslation('chat');
  const { t: tKnowledge } = useTranslation('knowledge');
  const { accessToken } = useAuth();
  const panelRef = useRef<HTMLDivElement>(null);

  // ── Local state (synced from session prop) ────────────────────────────────
  const [systemPrompt, setSystemPrompt] = useState(session.system_prompt ?? '');
  const [temperature, setTemperature] = useState(session.generation_params?.temperature ?? 0.7);
  const [topP, setTopP] = useState(session.generation_params?.top_p ?? 0.9);
  const [maxTokens, setMaxTokens] = useState(session.generation_params?.max_tokens ?? 0);
  const [unlimited, setUnlimited] = useState(!session.generation_params?.max_tokens);
  const [thinkingDefault, setThinkingDefault] = useState(session.generation_params?.thinking ?? false);
  const [selectedPreset, setSelectedPreset] = useState('Custom');

  // Model selector
  const [userModels, setUserModels] = useState<UserModel[]>([]);
  const [selectedModelRef, setSelectedModelRef] = useState(session.model_ref);
  const [modelsLoading, setModelsLoading] = useState(false);
  // A2A phase-2: optional composer model (in-turn prose delegation). '' = none.
  const [selectedComposerRef, setSelectedComposerRef] = useState(session.composer_model_ref ?? '');

  // K9.1 / W4: project picker — drives knowledge-service memory mode for
  // this session. The shared ProjectPicker self-loads active projects and
  // resolves a linked-but-archived project by id, so the panel no longer
  // owns a useProjects query or an archived-placeholder branch.
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(
    session.project_id,
  );

  // D-CHAT-01: debounce + accumulator. We coalesce all PATCHes that
  // arrive within the 500ms window into a single pending payload so
  // (a) close-during-debounce flushes the change instead of dropping
  // it, and (b) two unrelated edits (e.g. temperature then top_p)
  // don't clobber each other through the shared timer. The previous
  // implementation kept only the latest argument and lost the rest.
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingPatchRef = useRef<PatchSessionPayload | null>(null);
  // Held in a ref so the unmount cleanup can call the latest closure
  // without the effect re-subscribing on every render of the parent.
  const flushPendingRef = useRef<() => void>(() => undefined);

  // Load user models
  useEffect(() => {
    if (!accessToken) return;
    setModelsLoading(true);
    void aiModelsApi
      .listUserModels(accessToken, { include_inactive: false })
      .then((res) => setUserModels(res.items))
      .catch(() => {})
      .finally(() => setModelsLoading(false));
  }, [accessToken]);

  // Close on ESC
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  // Close on click outside (use mousedown to avoid conflict with open button)
  const openedAtRef = useRef(Date.now());
  useEffect(() => {
    openedAtRef.current = Date.now();
    function handleClick(e: MouseEvent) {
      // Ignore clicks within 150ms of opening (prevents instant close from trigger button)
      if (Date.now() - openedAtRef.current < 150) return;
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        onClose();
      }
    }
    window.addEventListener('mousedown', handleClick);
    return () => window.removeEventListener('mousedown', handleClick);
  }, [onClose]);

  // ── Save helper (debounced PATCH with flush-on-unmount) ───────────────────
  const flushPatch = useCallback(() => {
    const patch = pendingPatchRef.current;
    pendingPatchRef.current = null;
    if (saveTimerRef.current) {
      clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }
    if (!patch || !accessToken) return;
    void chatApi
      .patchSession(accessToken, session.session_id, patch)
      .then((updated) => onSessionUpdate(updated))
      .catch((err) => {
        toast.error(t('settings.save_failed', { error: (err as Error).message }));
      });
  }, [accessToken, session.session_id, onSessionUpdate]);

  // Keep the ref pointing at the latest flushPatch so unmount cleanup
  // (which only runs once with empty deps) calls the current closure.
  flushPendingRef.current = flushPatch;

  // Flush any pending patch on unmount instead of dropping it. The
  // dominant UX is "change one thing, click outside to dismiss" — that
  // close fires inside the debounce window, and the previous cleanup
  // (clearTimeout only) lost the change every time.
  useEffect(() => {
    return () => {
      flushPendingRef.current();
    };
  }, []);

  const patchSession = useCallback(
    (patch: PatchSessionPayload) => {
      if (!accessToken) return;
      // Merge into the pending payload. generation_params is nested
      // and each call passes only the fields the handler touched, so
      // it needs its own shallow merge — otherwise a temperature edit
      // followed by a top_p edit within 500ms would drop temperature.
      const prev = pendingPatchRef.current ?? {};
      const mergedGenParams =
        patch.generation_params || prev.generation_params
          ? { ...(prev.generation_params ?? {}), ...(patch.generation_params ?? {}) }
          : undefined;
      pendingPatchRef.current = {
        ...prev,
        ...patch,
        ...(mergedGenParams ? { generation_params: mergedGenParams } : {}),
      };
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
      saveTimerRef.current = setTimeout(() => {
        flushPatch();
      }, 500);
    },
    [accessToken, flushPatch],
  );

  // ── Handlers ──────────────────────────────────────────────────────────────
  function handleSystemPromptChange(value: string) {
    setSystemPrompt(value);
    patchSession({ system_prompt: value });
  }

  function handlePresetChange(preset: string) {
    setSelectedPreset(preset);
    if (preset !== 'Custom') {
      const prompt = SYSTEM_PROMPT_PRESETS[preset];
      setSystemPrompt(prompt);
      patchSession({ system_prompt: prompt });
    }
  }

  function handleTemperatureChange(value: number) {
    setTemperature(value);
    patchSession({ generation_params: { temperature: value } });
  }

  function handleTopPChange(value: number) {
    setTopP(value);
    patchSession({ generation_params: { top_p: value } });
  }

  function handleMaxTokensChange(value: number) {
    setMaxTokens(value);
    if (!unlimited) {
      patchSession({ generation_params: { max_tokens: value } });
    }
  }

  function handleUnlimitedToggle(checked: boolean) {
    setUnlimited(checked);
    patchSession({ generation_params: { max_tokens: checked ? null : (maxTokens || 4096) } });
  }

  function handleThinkingToggle(thinking: boolean) {
    setThinkingDefault(thinking);
    patchSession({ generation_params: { thinking } });
  }

  function handleModelChange(modelId: string) {
    setSelectedModelRef(modelId);
    patchSession({ model_source: 'user_model', model_ref: modelId });
  }

  function handleComposerChange(modelId: string) {
    // '' clears the composer (send explicit null so model_fields_set sees it).
    const next = modelId || null;
    setSelectedComposerRef(modelId);
    patchSession({
      composer_model_source: next ? 'user_model' : null,
      composer_model_ref: next,
    });
  }

  function handleProjectChange(next: string | null) {
    // ProjectPicker emits null on clear. Send explicit null so
    // chat-service's model_fields_set sees the unlink.
    setSelectedProjectId(next);
    patchSession({ project_id: next });
  }

  // ── Group models by provider ──────────────────────────────────────────────
  const groupedModels = userModels.reduce<Record<string, UserModel[]>>((acc, m) => {
    const key = m.provider_kind;
    if (!acc[key]) acc[key] = [];
    acc[key].push(m);
    return acc;
  }, {});

  return (
    <div
      ref={panelRef}
      className="fixed top-0 right-0 bottom-0 z-50 flex w-full flex-col border-l border-border bg-card shadow-[-8px_0_30px_rgba(0,0,0,0.4)] sm:w-[380px]"
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-5 py-4">
        <div className="flex items-center gap-2">
          <Settings className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold">{t('settings.title')}</h3>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded-md p-1.5 text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Scrollable body */}
      <div className="flex-1 overflow-y-auto p-5 space-y-5">

        {/* ── Model Selector ─────────────────────────────────────────── */}
        <div>
          <label className="mb-1.5 block text-xs font-medium text-muted-foreground">{t('settings.model')}</label>
          {modelsLoading ? (
            <div className="h-9 animate-pulse rounded-md bg-muted" />
          ) : (
            <select
              value={selectedModelRef}
              onChange={(e) => handleModelChange(e.target.value)}
              className="h-9 w-full rounded-md border border-border bg-background px-2 text-sm text-foreground outline-none focus:border-ring focus:shadow-[0_0_0_3px_rgba(212,149,42,0.2)]"
            >
              {Object.entries(groupedModels).map(([provider, models]) => (
                <optgroup key={provider} label={provider}>
                  {models.map((m) => (
                    <option key={m.user_model_id} value={m.user_model_id}>
                      {m.alias ?? m.provider_model_name}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          )}
        </div>

        {/* ── Composer model (A2A phase-2: in-turn prose delegation) ───── */}
        <div>
          <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
            {t('settings.composer_model', { defaultValue: 'Composer model (optional)' })}
          </label>
          {modelsLoading ? (
            <div className="h-9 animate-pulse rounded-md bg-muted" />
          ) : (
            <select
              value={selectedComposerRef}
              onChange={(e) => handleComposerChange(e.target.value)}
              className="h-9 w-full rounded-md border border-border bg-background px-2 text-sm text-foreground outline-none focus:border-ring focus:shadow-[0_0_0_3px_rgba(212,149,42,0.2)]"
            >
              <option value="">{t('settings.composer_none', { defaultValue: 'None — single model' })}</option>
              {Object.entries(groupedModels).map(([provider, models]) => (
                <optgroup key={provider} label={provider}>
                  {models.map((m) => (
                    <option key={m.user_model_id} value={m.user_model_id}>
                      {m.alias ?? m.provider_model_name}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          )}
          <p className="mt-1 text-[10px] text-muted-foreground">
            {t('settings.composer_hint', { defaultValue: 'When set, the AI can delegate prose-writing to this model via compose_prose (best: a reasoning model for writing + a tool-capable main model).' })}
          </p>
        </div>

        {/* ── Project (memory link) ──────────────────────────────────── */}
        <div>
          <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
            {tKnowledge('picker.label')}
          </label>
          <ProjectPicker
            value={selectedProjectId}
            onChange={handleProjectChange}
            placeholder={tKnowledge('picker.noProject')}
          />
          <p className="mt-1 text-[10px] text-muted-foreground">
            {tKnowledge('picker.hint')}
          </p>
        </div>

        {/* ── System Prompt ──────────────────────────────────────────── */}
        <div>
          <div className="mb-1.5 flex items-center justify-between">
            <label className="text-xs font-medium text-muted-foreground">{t('settings.system_prompt')}</label>
            <select
              value={selectedPreset}
              onChange={(e) => handlePresetChange(e.target.value)}
              className="bg-transparent border-none text-xs text-accent cursor-pointer outline-none"
            >
              {Object.keys(SYSTEM_PROMPT_PRESETS).map((p) => (
                <option key={p} value={p}>{t(`settings.preset.${p}`)}</option>
              ))}
            </select>
          </div>
          <textarea
            value={systemPrompt}
            onChange={(e) => handleSystemPromptChange(e.target.value)}
            placeholder={t('settings.prompt_placeholder')}
            className="min-h-[100px] w-full resize-y rounded-md border border-border bg-background p-2.5 text-xs leading-relaxed text-foreground placeholder:text-muted-foreground/50 outline-none focus:border-ring focus:shadow-[0_0_0_3px_rgba(212,149,42,0.2)]"
          />
        </div>

        {/* ── Generation Parameters ──────────────────────────────────── */}
        <details open>
          <summary className="mb-3 flex cursor-pointer items-center gap-1.5 text-xs font-medium text-muted-foreground">
            <svg className="h-2.5 w-2.5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path d="M19 9l-7 7-7-7" /></svg>
            {t('settings.gen_params')}
          </summary>

          {/* Max Tokens */}
          <div className="mb-4">
            <div className="mb-1.5 flex items-center justify-between">
              <label className="text-[11px] text-muted-foreground">{t('settings.max_tokens')}</label>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  value={unlimited ? '' : maxTokens}
                  onChange={(e) => handleMaxTokensChange(Number(e.target.value))}
                  disabled={unlimited}
                  placeholder="∞"
                  className="w-[70px] rounded border border-border bg-background px-2 py-1 text-right font-mono text-xs text-foreground outline-none focus:border-ring disabled:opacity-40"
                />
                <label className="flex items-center gap-1 text-[11px] text-muted-foreground cursor-pointer">
                  <input
                    type="checkbox"
                    checked={unlimited}
                    onChange={(e) => handleUnlimitedToggle(e.target.checked)}
                    className="accent-accent"
                  />
                  &#8734;
                </label>
              </div>
            </div>
            <input
              type="range"
              min={256}
              max={32768}
              step={256}
              value={unlimited ? 4096 : maxTokens}
              onChange={(e) => handleMaxTokensChange(Number(e.target.value))}
              disabled={unlimited}
              className="w-full accent-primary disabled:opacity-30"
            />
            <div className="flex justify-between text-[9px] text-muted-foreground">
              <span>256</span><span>32K</span>
            </div>
          </div>

          {/* Temperature */}
          <div className="mb-4">
            <div className="mb-1.5 flex items-center justify-between">
              <label className="text-[11px] text-muted-foreground">{t('settings.temperature')}</label>
              <span className="font-mono text-xs text-foreground">{temperature.toFixed(1)}</span>
            </div>
            <input
              type="range"
              min={0}
              max={2}
              step={0.1}
              value={temperature}
              onChange={(e) => handleTemperatureChange(Number(e.target.value))}
              className="w-full accent-primary"
            />
            <div className="flex justify-between text-[9px] text-muted-foreground">
              <span>{t('settings.temp_min')}</span><span>{t('settings.temp_max')}</span>
            </div>
          </div>

          {/* Top P */}
          <div className="mb-4">
            <div className="mb-1.5 flex items-center justify-between">
              <label className="text-[11px] text-muted-foreground">{t('settings.top_p')}</label>
              <span className="font-mono text-xs text-foreground">{topP.toFixed(2)}</span>
            </div>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={topP}
              onChange={(e) => handleTopPChange(Number(e.target.value))}
              className="w-full accent-primary"
            />
            <div className="flex justify-between text-[9px] text-muted-foreground">
              <span>{t('settings.topp_min')}</span><span>{t('settings.topp_max')}</span>
            </div>
          </div>

          {/* Thinking Mode Default */}
          <div className="mb-2">
            <div className="flex items-center justify-between">
              <label className="text-[11px] text-muted-foreground">{t('settings.default_mode')}</label>
              <div className="inline-flex rounded-md bg-secondary p-0.5 gap-0.5">
                <button
                  type="button"
                  onClick={() => handleThinkingToggle(true)}
                  className={`flex items-center gap-1 rounded px-2.5 py-1 text-[11px] font-medium transition-colors ${
                    thinkingDefault
                      ? 'bg-[#1e1633] text-[#a78bfa] border border-[#3b2d6b]'
                      : 'text-muted-foreground'
                  }`}
                >
                  <Brain className="h-2.5 w-2.5" />
                  {t('input.think')}
                </button>
                <button
                  type="button"
                  onClick={() => handleThinkingToggle(false)}
                  className={`flex items-center gap-1 rounded px-2.5 py-1 text-[11px] font-medium transition-colors ${
                    !thinkingDefault
                      ? 'bg-accent/10 text-accent border border-accent/30'
                      : 'text-muted-foreground'
                  }`}
                >
                  <Zap className="h-2.5 w-2.5" />
                  {t('input.fast')}
                </button>
              </div>
            </div>
          </div>
        </details>

        {/* ── Session Info ────────────────────────────────────────────── */}
        <div className="border-t border-border pt-4">
          <label className="mb-2.5 block text-xs font-medium text-muted-foreground">{t('settings.session_info')}</label>
          <div className="grid grid-cols-2 gap-2">
            <div className="rounded-md bg-secondary p-2.5">
              <p className="text-[10px] text-muted-foreground">{t('settings.messages')}</p>
              <p className="mt-0.5 font-mono text-base font-semibold">{session.message_count}</p>
            </div>
            <div className="rounded-md bg-secondary p-2.5">
              <p className="text-[10px] text-muted-foreground">{t('settings.status')}</p>
              <p className="mt-0.5 text-sm font-medium capitalize">{session.status}</p>
            </div>
            <div className="rounded-md bg-secondary p-2.5">
              <p className="text-[10px] text-muted-foreground">{t('settings.created')}</p>
              <p className="mt-0.5 text-sm font-medium">
                {new Date(session.created_at).toLocaleDateString()}
              </p>
            </div>
            <div className="rounded-md bg-secondary p-2.5">
              <p className="text-[10px] text-muted-foreground">{t('settings.pinned')}</p>
              <p className="mt-0.5 text-sm font-medium">{session.is_pinned ? t('settings.yes') : t('settings.no')}</p>
            </div>
          {/* Reset + Actions */}
          <div className="mt-4 flex gap-2">
            <button
              type="button"
              onClick={() => {
                setTemperature(0.7);
                setTopP(0.9);
                setMaxTokens(0);
                setUnlimited(true);
                setThinkingDefault(false);
                setSystemPrompt('');
                setSelectedPreset('Custom');
                patchSession({
                  system_prompt: '',
                  generation_params: { temperature: null, top_p: null, max_tokens: null, thinking: null },
                });
              }}
              className="flex-1 rounded-md border border-border px-3 py-2 text-xs text-muted-foreground hover:bg-secondary transition-colors"
            >
              {t('settings.reset')}
            </button>
          </div>
          </div>
        </div>
      </div>
    </div>
  );
}
