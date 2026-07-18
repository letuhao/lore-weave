import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { PROMPT_PRESETS } from '../prompts/presets';
import { MessageSquare, X } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { defaultModelsApi, CHAT_CAPABILITY } from '@/features/settings/api';
import { ModelPicker, useUserModels } from '@/components/model-picker';
import type { GenerationParams } from '../types';

// `key` → i18n label; `prompt` stays English (it is an LLM system directive).
// The ONE preset list (../prompts/presets). This file used to declare its own 4 presets
// with lowercase keys and slightly different prompt TEXT than SessionSettingsPanel's 6 —
// so the prompt a new chat was seeded with was not the prompt the settings panel showed
// you under that name, and re-picking it there silently rewrote your system prompt.
const PRESETS = PROMPT_PRESETS;

interface NewChatDialogProps {
  open: boolean;
  onClose: () => void;
  onCreate: (modelRef: string, systemPrompt?: string, generationParams?: GenerationParams) => void;
}

export function NewChatDialog({ open, onClose, onCreate }: NewChatDialogProps) {
  const { t } = useTranslation('chat');
  const { accessToken } = useAuth();
  const [selectedModel, setSelectedModel] = useState('');
  const [systemPrompt, setSystemPrompt] = useState('');
  const [selectedPreset, setSelectedPreset] = useState<number | null>(null);
  const [showPrompt, setShowPrompt] = useState(false);
  const [creating, setCreating] = useState(false);

  // W5: the shared picker owns fetch/search/grouping — capability="chat" fixes
  // the old "rerankers offered in the chat picker" bug (server-side filter).
  const { models: userModels, loading } = useUserModels({
    capability: CHAT_CAPABILITY,
    enabled: open,
  });

  // Pre-select: the user's default chat model (Settings → Default models) when
  // set and still listed, else the first model (server order = favorites first).
  useEffect(() => {
    if (!open || !accessToken || selectedModel || !userModels || userModels.length === 0) return;
    let cancelled = false;
    void defaultModelsApi
      .get(accessToken)
      .catch(() => ({ defaults: {} as Record<string, string> }))
      .then(({ defaults }) => {
        if (cancelled) return;
        const preferred = defaults[CHAT_CAPABILITY];
        const match = preferred && userModels.some((m) => m.user_model_id === preferred);
        setSelectedModel(match ? preferred : userModels[0].user_model_id);
      });
    return () => {
      cancelled = true;
    };
  }, [open, accessToken, userModels, selectedModel]);

  // Reset on close
  useEffect(() => {
    if (!open) {
      setSystemPrompt('');
      setSelectedPreset(null);
      setShowPrompt(false);
    }
  }, [open]);

  // Selected model info
  const selectedModelInfo = (userModels ?? []).find((m) => m.user_model_id === selectedModel);

  function handlePresetClick(index: number) {
    if (selectedPreset === index) {
      setSelectedPreset(null);
      setSystemPrompt('');
    } else {
      setSelectedPreset(index);
      setSystemPrompt(PRESETS[index].prompt);
      setShowPrompt(true);
    }
  }

  function handleCreate() {
    setCreating(true);
    // onCreate is called by parent (may be sync or async) — always reset creating
    try {
      onCreate(
        selectedModel,
        systemPrompt || undefined,
        undefined,
      );
    } catch (err) {
      toast.error(t('new.create_failed', { error: (err as Error).message }));
    } finally {
      // Reset after a short delay to prevent double-clicks but not permanently disable
      setTimeout(() => setCreating(false), 1000);
    }
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose} data-testid="new-chat-dialog">
      <div
        className="w-full max-w-md rounded-lg border bg-card p-5 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-sm font-semibold">{t('new.title')}</h3>
          <button type="button" onClick={onClose} data-testid="new-chat-dismiss" className="rounded p-1 text-muted-foreground hover:bg-secondary hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-4">
          {/* Model selector — shared ModelPicker (search / favorites / recents) */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">{t('new.model')}</label>
            <ModelPicker
              capability={CHAT_CAPABILITY}
              value={selectedModel || null}
              onChange={(id) => setSelectedModel(id ?? '')}
              ariaLabel={t('new.model')}
              placeholder={t('new.search_models')}
              emptyState={<p className="text-xs text-muted-foreground">{t('new.no_models')}</p>}
            />

            {/* Capability badges */}
            {selectedModelInfo && (
              <div className="flex gap-1.5 flex-wrap mt-1">
                <span className="inline-flex items-center gap-1 rounded-full bg-secondary px-2 py-0.5 text-[10px] text-muted-foreground">
                  <MessageSquare className="h-2.5 w-2.5" />
                  {selectedModelInfo.provider_kind}
                </span>
                {selectedModelInfo.context_length && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-accent/10 px-2 py-0.5 text-[10px] text-accent">
                    {t('new.ctx', { n: Math.round(selectedModelInfo.context_length / 1024) })}
                  </span>
                )}
                {selectedModelInfo.is_favorite && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-[10px] text-primary">
                    &#9733; {t('new.favorite')}
                  </span>
                )}
              </div>
            )}
          </div>

          {/* Quick-start presets */}
          <div>
            <label className="mb-1.5 block text-xs font-medium text-muted-foreground">{t('new.quick_start')}</label>
            <div className="grid grid-cols-2 gap-2">
              {PRESETS.map((p, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => handlePresetClick(i)}
                  className={`rounded-md border p-2.5 text-left transition-colors ${
                    selectedPreset === i
                      ? 'border-accent bg-accent/5'
                      : 'border-border hover:border-border hover:bg-secondary/50'
                  }`}
                >
                  <span className="text-base">{p.icon}</span>
                  {/* The shared registry renamed `novel`→`novelist` and added `analyst`, so a locale
                      that predates it has no key — fall back to the registry's English label
                      rather than rendering the raw key at the user. */}
                  <p className="mt-0.5 text-[11px] font-medium text-foreground">
                    {t(`presets.${p.key}`, { defaultValue: p.label })}
                  </p>
                </button>
              ))}
            </div>
          </div>

          {/* System prompt (expandable) */}
          <div>
            <button
              type="button"
              onClick={() => setShowPrompt(!showPrompt)}
              className="text-xs text-accent hover:underline"
            >
              {showPrompt ? t('new.hide_prompt') : t('new.add_prompt')}
            </button>
            {showPrompt && (
              <textarea
                value={systemPrompt}
                onChange={(e) => { setSystemPrompt(e.target.value); setSelectedPreset(null); }}
                placeholder={t('new.prompt_placeholder')}
                className="mt-1.5 min-h-[80px] w-full resize-y rounded-md border border-border bg-background p-2.5 text-xs leading-relaxed text-foreground placeholder:text-muted-foreground/50 outline-none focus:border-ring"
              />
            )}
          </div>

          <button
            type="button"
            className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:brightness-110 disabled:opacity-50"
            disabled={!selectedModel || loading || creating}
            onClick={handleCreate}
          >
            {t('new.start_chat')}
          </button>
        </div>
      </div>
    </div>
  );
}
