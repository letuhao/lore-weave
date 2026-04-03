import { useEffect, useMemo, useState } from 'react';
import { Brain, MessageSquare, Search, X } from 'lucide-react';
import { useAuth } from '@/auth';
import { aiModelsApi, type UserModel } from '@/features/ai-models/api';
import type { CreateSessionPayload, GenerationParams } from '../types';

const PRESETS: { label: string; prompt: string; icon: string }[] = [
  { label: 'Novel Assistant', icon: '📖', prompt: 'You are a creative writing assistant specializing in novels. Analyze character arcs, plot structure, and worldbuilding. Provide concrete scene rewrites when suggesting changes.' },
  { label: 'Translator', icon: '🌐', prompt: 'You are a literary translator. Preserve tone, style, and nuance. Explain translation choices involving cultural adaptation or idioms.' },
  { label: 'Worldbuilder', icon: '🗺️', prompt: 'You are a worldbuilding consultant. Help create consistent magic systems, politics, geography, and cultures. Flag inconsistencies.' },
  { label: 'Editor', icon: '✏️', prompt: 'You are a professional book editor. Focus on pacing, dialogue, show-vs-tell, and narrative voice. Be specific and constructive.' },
];

interface NewChatDialogProps {
  open: boolean;
  onClose: () => void;
  onCreate: (modelRef: string, systemPrompt?: string, generationParams?: GenerationParams) => void;
}

export function NewChatDialog({ open, onClose, onCreate }: NewChatDialogProps) {
  const { accessToken } = useAuth();
  const [userModels, setUserModels] = useState<UserModel[]>([]);
  const [selectedModel, setSelectedModel] = useState('');
  const [modelSearch, setModelSearch] = useState('');
  const [systemPrompt, setSystemPrompt] = useState('');
  const [selectedPreset, setSelectedPreset] = useState<number | null>(null);
  const [showPrompt, setShowPrompt] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !accessToken) return;
    setLoading(true);
    void aiModelsApi
      .listUserModels(accessToken, { include_inactive: false })
      .then((res) => {
        setUserModels(res.items);
        if (res.items.length > 0 && !selectedModel) {
          // Pre-select favorite or first
          const fav = res.items.find((m) => m.is_favorite);
          setSelectedModel((fav ?? res.items[0]).user_model_id);
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [open, accessToken]);

  // Reset on close
  useEffect(() => {
    if (!open) {
      setModelSearch('');
      setSystemPrompt('');
      setSelectedPreset(null);
      setShowPrompt(false);
    }
  }, [open]);

  // Group + filter models
  const groupedModels = useMemo(() => {
    const q = modelSearch.toLowerCase();
    const filtered = q
      ? userModels.filter((m) => (m.alias ?? m.provider_model_name).toLowerCase().includes(q) || m.provider_kind.toLowerCase().includes(q))
      : userModels;
    return filtered.reduce<Record<string, UserModel[]>>((acc, m) => {
      const key = m.provider_kind;
      if (!acc[key]) acc[key] = [];
      acc[key].push(m);
      return acc;
    }, {});
  }, [userModels, modelSearch]);

  // Selected model info
  const selectedModelInfo = userModels.find((m) => m.user_model_id === selectedModel);

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
    onCreate(
      selectedModel,
      systemPrompt || undefined,
      undefined,
    );
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div
        className="w-full max-w-md rounded-lg border bg-card p-5 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-sm font-semibold">Start New Chat</h3>
          <button type="button" onClick={onClose} className="rounded p-1 text-muted-foreground hover:bg-secondary hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-4">
          {/* Model selector with search */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">Model</label>
            {loading ? (
              <div className="h-9 animate-pulse rounded-md bg-muted" />
            ) : userModels.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                No active models. Add one in Settings &rarr; Providers.
              </p>
            ) : (
              <>
                <div className="relative">
                  <Search className="absolute left-2.5 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground" />
                  <input
                    type="text"
                    value={modelSearch}
                    onChange={(e) => setModelSearch(e.target.value)}
                    placeholder="Search models..."
                    className="w-full rounded-t-md border border-border bg-background py-1.5 pl-7 pr-2 text-xs text-foreground placeholder:text-muted-foreground outline-none focus:border-ring"
                  />
                </div>
                <select
                  value={selectedModel}
                  onChange={(e) => setSelectedModel(e.target.value)}
                  size={Math.min(Object.values(groupedModels).flat().length + Object.keys(groupedModels).length, 6)}
                  className="w-full rounded-b-md border border-t-0 border-border bg-background px-1 py-1 text-sm text-foreground outline-none focus:border-ring"
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
              </>
            )}

            {/* Capability badges */}
            {selectedModelInfo && (
              <div className="flex gap-1.5 flex-wrap mt-1">
                <span className="inline-flex items-center gap-1 rounded-full bg-secondary px-2 py-0.5 text-[10px] text-muted-foreground">
                  <MessageSquare className="h-2.5 w-2.5" />
                  {selectedModelInfo.provider_kind}
                </span>
                {selectedModelInfo.context_length && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-accent/10 px-2 py-0.5 text-[10px] text-accent">
                    {Math.round(selectedModelInfo.context_length / 1024)}K ctx
                  </span>
                )}
                {selectedModelInfo.is_favorite && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-[10px] text-primary">
                    &#9733; Favorite
                  </span>
                )}
              </div>
            )}
          </div>

          {/* Quick-start presets */}
          <div>
            <label className="mb-1.5 block text-xs font-medium text-muted-foreground">Quick Start</label>
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
                  <p className="mt-0.5 text-[11px] font-medium text-foreground">{p.label}</p>
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
              {showPrompt ? 'Hide' : 'Add'} system prompt
            </button>
            {showPrompt && (
              <textarea
                value={systemPrompt}
                onChange={(e) => { setSystemPrompt(e.target.value); setSelectedPreset(null); }}
                placeholder="Custom instructions for the AI..."
                className="mt-1.5 min-h-[80px] w-full resize-y rounded-md border border-border bg-background p-2.5 text-xs leading-relaxed text-foreground placeholder:text-muted-foreground/50 outline-none focus:border-ring"
              />
            )}
          </div>

          <button
            type="button"
            className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:brightness-110 disabled:opacity-50"
            disabled={!selectedModel || loading}
            onClick={handleCreate}
          >
            Start Chat
          </button>
        </div>
      </div>
    </div>
  );
}
