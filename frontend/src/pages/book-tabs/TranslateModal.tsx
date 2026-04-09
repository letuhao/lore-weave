import { useEffect, useState, useMemo } from 'react';
import { toast } from 'sonner';
import { Loader2, AlertTriangle } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useAuth } from '@/auth';
import { booksApi, type Chapter } from '@/features/books/api';
import { translationApi, type BookTranslationSettings } from '@/features/translation/api';
import { aiModelsApi, type UserModel } from '@/features/ai-models/api';
import { getLanguageName, LANGUAGE_NAMES } from '@/lib/languages';
import { cn } from '@/lib/utils';

interface TranslateModalProps {
  open: boolean;
  onClose: () => void;
  bookId: string;
  onJobCreated: () => void;
}

export function TranslateModal({ open, onClose, bookId, onJobCreated }: TranslateModalProps) {
  const { accessToken } = useAuth();
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [settings, setSettings] = useState<BookTranslationSettings | null>(null);
  const [userModels, setUserModels] = useState<UserModel[]>([]);
  const [loading, setLoading] = useState(true);

  const [selectedChapters, setSelectedChapters] = useState<Set<string>>(new Set());
  const [selectedLang, setSelectedLang] = useState('');
  const [selectedModelRef, setSelectedModelRef] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open || !accessToken) return;
    setLoading(true);
    Promise.all([
      booksApi.listChapters(accessToken, bookId, { lifecycle_state: 'active', limit: 200, offset: 0 }),
      translationApi.getBookSettings(accessToken, bookId).catch(() => null),
      aiModelsApi.listUserModels(accessToken).catch(() => ({ items: [] })),
    ])
      .then(([chs, bkSettings, modelsResp]) => {
        setChapters(chs.items);
        setSettings(bkSettings);
        setUserModels(modelsResp.items.filter((m) => m.is_active));
        setSelectedLang(bkSettings?.target_language || '');
        setSelectedModelRef(bkSettings?.model_ref || '');
        setSelectedChapters(new Set(chs.items.map((c) => c.chapter_id)));
      })
      .catch((e) => toast.error((e as Error).message))
      .finally(() => setLoading(false));
  }, [open, accessToken, bookId]);

  // Group models by provider
  const modelsByProvider = useMemo(() => {
    const map = new Map<string, UserModel[]>();
    for (const m of userModels) {
      const key = m.provider_kind;
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(m);
    }
    return map;
  }, [userModels]);

  const toggleChapter = (id: string) => {
    setSelectedChapters((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    if (selectedChapters.size === chapters.length) {
      setSelectedChapters(new Set());
    } else {
      setSelectedChapters(new Set(chapters.map((c) => c.chapter_id)));
    }
  };

  const handleSaveSettings = async (lang: string, modelRef: string) => {
    if (!accessToken) return;
    try {
      const payload: Record<string, unknown> = {};
      if (lang) payload.target_language = lang;
      if (modelRef) payload.model_ref = modelRef;
      payload.model_source = 'user_model';
      const updated = await translationApi.putBookSettings(accessToken, bookId, payload);
      setSettings(updated);
    } catch {
      // Silent — settings save is best-effort, job will use current values
    }
  };

  const handleLangChange = (lang: string) => {
    setSelectedLang(lang);
    void handleSaveSettings(lang, selectedModelRef);
  };

  const handleModelChange = (modelRef: string) => {
    setSelectedModelRef(modelRef);
    void handleSaveSettings(selectedLang, modelRef);
  };

  const canSubmit = !!selectedLang && !!selectedModelRef && selectedChapters.size > 0 && !submitting;

  const handleSubmit = async () => {
    if (!accessToken || !canSubmit) return;
    setSubmitting(true);
    try {
      await translationApi.createJob(accessToken, bookId, {
        chapter_ids: [...selectedChapters],
      });
      toast.success(`Translation job started for ${selectedChapters.size} chapter(s)`);
      onJobCreated();
      onClose();
    } catch (e) {
      const err = e as Error & { code?: string };
      if (err.code === 'TRANSL_NO_MODEL_CONFIGURED') {
        toast.error('No model configured. Please select a model above.');
      } else {
        toast.error(err.message || 'Translation failed');
      }
    }
    setSubmitting(false);
  };

  if (!open) return null;

  const availableLangs = Object.entries(LANGUAGE_NAMES);
  const selectedModel = userModels.find((m) => m.user_model_id === selectedModelRef);

  return (
    <>
      <div className="fixed inset-0 z-50 bg-black/50" onClick={onClose} />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div
          className="w-full max-w-lg rounded-lg border bg-background shadow-xl"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="border-b px-5 py-4">
            <h2 className="text-sm font-semibold">Translate Chapters</h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              Select language, model, and chapters to translate
            </p>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <div className="px-5 py-4 space-y-4">
              {/* Language + Model row */}
              <div className="grid grid-cols-2 gap-3">
                {/* Language */}
                <div>
                  <label className="mb-1 block text-xs font-medium">Target Language</label>
                  <select
                    value={selectedLang}
                    onChange={(e) => handleLangChange(e.target.value)}
                    className="h-9 w-full rounded-md border bg-background px-3 text-[13px] focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
                  >
                    <option value="">Select language...</option>
                    {availableLangs.map(([code, name]) => (
                      <option key={code} value={code}>{name} ({code})</option>
                    ))}
                  </select>
                </div>

                {/* Model */}
                <div>
                  <label className="mb-1 block text-xs font-medium">Model</label>
                  {userModels.length === 0 ? (
                    <div className="flex h-9 items-center rounded-md border border-dashed bg-background px-3 text-[11px] text-muted-foreground">
                      No models.{' '}
                      <Link to="/settings" onClick={onClose} className="ml-1 text-primary hover:underline">
                        Add in Settings
                      </Link>
                    </div>
                  ) : (
                    <select
                      value={selectedModelRef}
                      onChange={(e) => handleModelChange(e.target.value)}
                      className="h-9 w-full rounded-md border bg-background px-3 text-[13px] focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
                    >
                      <option value="">Select model...</option>
                      {Array.from(modelsByProvider.entries()).map(([provider, models]) => (
                        <optgroup key={provider} label={provider}>
                          {models.map((m) => (
                            <option key={m.user_model_id} value={m.user_model_id}>
                              {m.alias || m.provider_model_name}
                            </option>
                          ))}
                        </optgroup>
                      ))}
                    </select>
                  )}
                </div>
              </div>

              {/* Model info */}
              {selectedModel && (
                <p className="text-[10px] text-muted-foreground -mt-2">
                  {selectedModel.provider_kind} — <span className="font-mono">{selectedModel.provider_model_name}</span>
                </p>
              )}

              {/* Warning: missing config */}
              {(!selectedLang || !selectedModelRef) && (
                <div className="flex items-center gap-2 rounded-md border border-amber-400/20 bg-amber-400/5 px-3 py-2">
                  <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-amber-400" />
                  <p className="text-[11px] text-amber-400">
                    {!selectedLang && !selectedModelRef
                      ? 'Select a target language and model to start translating.'
                      : !selectedLang
                        ? 'Select a target language.'
                        : 'Select a model to use for translation.'}
                  </p>
                </div>
              )}

              {/* Chapter selection */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-xs font-medium text-muted-foreground">
                    Chapters ({selectedChapters.size}/{chapters.length})
                  </label>
                  <button
                    onClick={toggleAll}
                    className="text-[10px] text-primary hover:underline"
                  >
                    {selectedChapters.size === chapters.length ? 'Deselect all' : 'Select all'}
                  </button>
                </div>
                <div className="max-h-48 overflow-y-auto rounded-md border">
                  {chapters.map((ch, i) => (
                    <label
                      key={ch.chapter_id}
                      className={cn(
                        'flex items-center gap-3 px-3 py-2 text-xs cursor-pointer hover:bg-card transition-colors',
                        i < chapters.length - 1 && 'border-b',
                      )}
                    >
                      <input
                        type="checkbox"
                        checked={selectedChapters.has(ch.chapter_id)}
                        onChange={() => toggleChapter(ch.chapter_id)}
                        className="h-3.5 w-3.5 rounded border-border accent-primary"
                      />
                      <span className="w-5 text-right font-mono text-muted-foreground">{i + 1}</span>
                      <span className="flex-1 line-clamp-1">
                        {ch.title || ch.original_filename || 'Untitled'}
                      </span>
                    </label>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Footer */}
          <div className="flex items-center justify-end gap-2 border-t px-5 py-3">
            <button
              onClick={onClose}
              className="rounded-md border px-4 py-1.5 text-xs font-medium text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={() => void handleSubmit()}
              disabled={!canSubmit}
              className="inline-flex items-center gap-1.5 rounded-md bg-primary px-4 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {submitting && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              Start Translation
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
