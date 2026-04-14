import { useCallback, useEffect, useRef, useState } from 'react';
import { Settings, X, Brain, Zap } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { aiModelsApi, type UserModel } from '@/features/ai-models/api';
import { useProjects } from '@/features/knowledge/hooks/useProjects';
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

  // K9.1: project picker — drives knowledge-service memory mode for
  // this session. Only non-archived projects show in the dropdown so
  // users can't link a session to something they've shelved.
  const {
    items: projects,
    isLoading: projectsLoading,
  } = useProjects(false);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(
    session.project_id,
  );

  // Debounce timer
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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

  // Cleanup debounce timer on unmount
  useEffect(() => {
    return () => {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    };
  }, []);

  // ── Save helper (debounced PATCH) ─────────────────────────────────────────
  const patchSession = useCallback(
    (patch: PatchSessionPayload) => {
      if (!accessToken) return;
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
      saveTimerRef.current = setTimeout(() => {
        void chatApi.patchSession(accessToken, session.session_id, patch).then((updated) => {
          onSessionUpdate(updated);
        }).catch((err) => {
          toast.error(`Save failed: ${(err as Error).message}`);
        });
      }, 500);
    },
    [accessToken, session.session_id, onSessionUpdate],
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

  function handleProjectChange(value: string) {
    // Empty string from the "No project" option clears the link.
    // Send explicit null so chat-service's model_fields_set sees it.
    const next = value === '' ? null : value;
    setSelectedProjectId(next);
    // K9.1-R1: bypass the shared debounce. The picker is a single
    // discrete commit, not a typing buffer — and the dominant UX
    // pattern is "pick, click-outside to close" which fires the
    // panel unmount inside the 500ms debounce window. The unmount
    // cleanup at line 81 would clear the pending timer and the
    // PATCH would never be sent. Calling chatApi directly here
    // makes the change durable. The pre-existing close-during-
    // debounce bug also affects every other field on this panel
    // (model selector especially) and is tracked as D-CHAT-01.
    if (!accessToken) return;
    void chatApi
      .patchSession(accessToken, session.session_id, { project_id: next })
      .then((updated) => onSessionUpdate(updated))
      .catch((err) => {
        toast.error(`Save failed: ${(err as Error).message}`);
      });
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
          <h3 className="text-sm font-semibold">Session Settings</h3>
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
          <label className="mb-1.5 block text-xs font-medium text-muted-foreground">Model</label>
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

        {/* ── Project (memory link) ──────────────────────────────────── */}
        <div>
          <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
            Project memory
          </label>
          {projectsLoading ? (
            <div className="h-9 animate-pulse rounded-md bg-muted" />
          ) : (
            <select
              aria-label="Project memory"
              value={selectedProjectId ?? ''}
              onChange={(e) => handleProjectChange(e.target.value)}
              className="h-9 w-full rounded-md border border-border bg-background px-2 text-sm text-foreground outline-none focus:border-ring focus:shadow-[0_0_0_3px_rgba(212,149,42,0.2)]"
            >
              <option value="">No project — global memory only</option>
              {projects.map((p) => (
                <option key={p.project_id} value={p.project_id}>
                  {p.name}
                </option>
              ))}
              {/* K9.1-R5: if the linked project was archived after this
                  session was created, it won't be in the active list.
                  Surface it as a disabled placeholder so the <select>
                  value stays valid and the user can see why their
                  memory link looks broken. */}
              {selectedProjectId &&
                !projects.some((p) => p.project_id === selectedProjectId) && (
                  <option value={selectedProjectId} disabled>
                    (archived project — pick another)
                  </option>
                )}
            </select>
          )}
          <p className="mt-1 text-[10px] text-muted-foreground">
            Links this chat to a knowledge-service project so the AI sees its
            summary and glossary on every turn.
          </p>
        </div>

        {/* ── System Prompt ──────────────────────────────────────────── */}
        <div>
          <div className="mb-1.5 flex items-center justify-between">
            <label className="text-xs font-medium text-muted-foreground">System Prompt</label>
            <select
              value={selectedPreset}
              onChange={(e) => handlePresetChange(e.target.value)}
              className="bg-transparent border-none text-xs text-accent cursor-pointer outline-none"
            >
              {Object.keys(SYSTEM_PROMPT_PRESETS).map((p) => (
                <option key={p}>{p}</option>
              ))}
            </select>
          </div>
          <textarea
            value={systemPrompt}
            onChange={(e) => handleSystemPromptChange(e.target.value)}
            placeholder="Give the AI a role, personality, or specific instructions..."
            className="min-h-[100px] w-full resize-y rounded-md border border-border bg-background p-2.5 text-xs leading-relaxed text-foreground placeholder:text-muted-foreground/50 outline-none focus:border-ring focus:shadow-[0_0_0_3px_rgba(212,149,42,0.2)]"
          />
        </div>

        {/* ── Generation Parameters ──────────────────────────────────── */}
        <details open>
          <summary className="mb-3 flex cursor-pointer items-center gap-1.5 text-xs font-medium text-muted-foreground">
            <svg className="h-2.5 w-2.5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path d="M19 9l-7 7-7-7" /></svg>
            Generation Parameters
          </summary>

          {/* Max Tokens */}
          <div className="mb-4">
            <div className="mb-1.5 flex items-center justify-between">
              <label className="text-[11px] text-muted-foreground">Max Tokens</label>
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
              <label className="text-[11px] text-muted-foreground">Temperature</label>
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
              <span>0 (precise)</span><span>2 (creative)</span>
            </div>
          </div>

          {/* Top P */}
          <div className="mb-4">
            <div className="mb-1.5 flex items-center justify-between">
              <label className="text-[11px] text-muted-foreground">Top P</label>
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
              <span>0 (narrow)</span><span>1 (diverse)</span>
            </div>
          </div>

          {/* Thinking Mode Default */}
          <div className="mb-2">
            <div className="flex items-center justify-between">
              <label className="text-[11px] text-muted-foreground">Default Mode</label>
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
                  Think
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
                  Fast
                </button>
              </div>
            </div>
          </div>
        </details>

        {/* ── Session Info ────────────────────────────────────────────── */}
        <div className="border-t border-border pt-4">
          <label className="mb-2.5 block text-xs font-medium text-muted-foreground">Session Info</label>
          <div className="grid grid-cols-2 gap-2">
            <div className="rounded-md bg-secondary p-2.5">
              <p className="text-[10px] text-muted-foreground">Messages</p>
              <p className="mt-0.5 font-mono text-base font-semibold">{session.message_count}</p>
            </div>
            <div className="rounded-md bg-secondary p-2.5">
              <p className="text-[10px] text-muted-foreground">Status</p>
              <p className="mt-0.5 text-sm font-medium capitalize">{session.status}</p>
            </div>
            <div className="rounded-md bg-secondary p-2.5">
              <p className="text-[10px] text-muted-foreground">Created</p>
              <p className="mt-0.5 text-sm font-medium">
                {new Date(session.created_at).toLocaleDateString()}
              </p>
            </div>
            <div className="rounded-md bg-secondary p-2.5">
              <p className="text-[10px] text-muted-foreground">Pinned</p>
              <p className="mt-0.5 text-sm font-medium">{session.is_pinned ? 'Yes' : 'No'}</p>
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
              Reset to Defaults
            </button>
          </div>
          </div>
        </div>
      </div>
    </div>
  );
}
