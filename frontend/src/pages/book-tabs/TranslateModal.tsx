import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Loader2 } from 'lucide-react';
import { useAuth } from '@/auth';
import { booksApi, type Chapter } from '@/features/books/api';
import { translationApi, type BookTranslationSettings } from '@/features/translation/api';
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
  const [loading, setLoading] = useState(true);

  const [selectedChapters, setSelectedChapters] = useState<Set<string>>(new Set());
  const [submitting, setSubmitting] = useState(false);
  const [selectedLang, setSelectedLang] = useState('');

  useEffect(() => {
    if (!open || !accessToken) return;
    setLoading(true);
    Promise.all([
      booksApi.listChapters(accessToken, bookId, { lifecycle_state: 'active', limit: 200, offset: 0 }),
      translationApi.getBookSettings(accessToken, bookId).catch(() => null),
    ])
      .then(([chs, bkSettings]) => {
        setChapters(chs.items);
        setSettings(bkSettings);
        setSelectedLang(bkSettings?.target_language || '');
        setSelectedChapters(new Set(chs.items.map((c) => c.chapter_id)));
      })
      .catch((e) => toast.error((e as Error).message))
      .finally(() => setLoading(false));
  }, [open, accessToken, bookId]);

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

  const handleLangChange = async (lang: string) => {
    setSelectedLang(lang);
    if (!accessToken || !lang) return;
    try {
      const updated = await translationApi.putBookSettings(accessToken, bookId, { target_language: lang });
      setSettings(updated);
    } catch {
      toast.error('Failed to save language setting');
    }
  };

  const targetLang = selectedLang || settings?.target_language;
  const hasModel = !!settings?.model_ref;

  // Available languages: exclude source language of the book
  const availableLangs = Object.entries(LANGUAGE_NAMES);

  const handleSubmit = async () => {
    if (!accessToken || !targetLang || selectedChapters.size === 0 || !hasModel) return;
    setSubmitting(true);
    try {
      await translationApi.createJob(accessToken, bookId, {
        chapter_ids: [...selectedChapters],
      });
      toast.success(`Translation job started for ${selectedChapters.size} chapter(s)`);
      onJobCreated();
      onClose();
    } catch (e) {
      toast.error((e as Error).message);
    }
    setSubmitting(false);
  };

  if (!open) return null;

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-50 bg-black/50" onClick={onClose} />

      {/* Modal */}
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div
          className="w-full max-w-lg rounded-lg border bg-background shadow-xl"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="border-b px-5 py-4">
            <h2 className="text-sm font-semibold">Translate Chapters</h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              Select target language and chapters to translate
            </p>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <div className="px-5 py-4 space-y-4">
              {/* Target language selector */}
              <div className="rounded-md border bg-card px-4 py-3 space-y-2">
                <label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider block">
                  Target Language
                </label>
                <select
                  value={selectedLang}
                  onChange={(e) => void handleLangChange(e.target.value)}
                  className="w-full rounded-md border bg-background px-3 py-2 text-sm font-medium focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
                >
                  <option value="">Select a language...</option>
                  {availableLangs.map(([code, name]) => (
                    <option key={code} value={code}>{name} ({code})</option>
                  ))}
                </select>
                {!hasModel && targetLang && (
                  <p className="text-[10px] text-amber-400">
                    No translation model configured. Set a model in Settings → Translation first.
                  </p>
                )}
              </div>

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
              disabled={submitting || !targetLang || !hasModel || selectedChapters.size === 0}
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
