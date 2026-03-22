import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useAuth } from '@/auth';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { LanguagePicker } from '@/components/books/LanguagePicker';
import { ModelSelector } from '@/components/translation/ModelSelector';
import { PromptEditor } from '@/components/translation/PromptEditor';
import { TranslateButton } from '@/components/translation/TranslateButton';
import { ChapterTranslationPanel } from '@/components/translation/ChapterTranslationPanel';
import { translationApi, type BookTranslationSettings, type TranslationJob, type ModelSource } from '@/features/translation/api';
import { booksApi, type Chapter } from '@/features/books/api';

type FormState = {
  target_language: string;
  model_source: ModelSource;
  model_ref: string | null;
  system_prompt: string;
  user_prompt_tpl: string;
};

function settingsToForm(s: BookTranslationSettings): FormState {
  return {
    target_language: s.target_language,
    model_source: s.model_source,
    model_ref: s.model_ref,
    system_prompt: s.system_prompt,
    user_prompt_tpl: s.user_prompt_tpl,
  };
}

export default function BookTranslationPage() {
  const { bookId } = useParams<{ bookId: string }>();
  const { accessToken } = useAuth();
  const token = accessToken!;

  const [loadingSettings, setLoadingSettings] = useState(true);
  const [loadingChapters, setLoadingChapters] = useState(true);
  const [loadingJobs, setLoadingJobs] = useState(true);

  const [settings, setSettings] = useState<BookTranslationSettings | null>(null);
  const [form, setForm] = useState<FormState | null>(null);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [jobs, setJobs] = useState<TranslationJob[]>([]);

  // Pre-select all chapters that have no completed translation
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState('');
  const [saveSuccess, setSaveSuccess] = useState('');

  useEffect(() => {
    if (!bookId) return;

    translationApi.getBookSettings(token, bookId)
      .then((s) => { setSettings(s); setForm(settingsToForm(s)); })
      .finally(() => setLoadingSettings(false));

    booksApi.listChapters(token, bookId, { lifecycle_state: 'active', limit: 100 })
      .then((r) => setChapters(r.items))
      .finally(() => setLoadingChapters(false));

    translationApi.listJobs(token, bookId, { limit: 5 })
      .then(setJobs)
      .finally(() => setLoadingJobs(false));
  }, [token, bookId]);

  // Pre-select untranslated chapters once chapters + jobs are loaded
  useEffect(() => {
    if (loadingChapters || loadingJobs) return;
    const translatedIds = new Set(
      jobs
        .filter((j) => j.status === 'completed' || j.status === 'partial')
        .flatMap((j) => j.chapter_ids),
    );
    const untranslated = chapters
      .filter((c) => !translatedIds.has(c.chapter_id))
      .map((c) => c.chapter_id);
    setSelectedIds(untranslated.length > 0 ? untranslated : chapters.map((c) => c.chapter_id));
  }, [loadingChapters, loadingJobs, chapters, jobs]);

  function toggleChapter(id: string) {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  }

  async function handleSave() {
    if (!form || !bookId) return;
    if (!form.model_ref) { setSaveError('Please select a model.'); return; }
    if (!form.user_prompt_tpl.includes('{chapter_text}')) {
      setSaveError('User prompt template must contain {chapter_text}.');
      return;
    }
    setSaving(true); setSaveError(''); setSaveSuccess('');
    try {
      const saved = await translationApi.putBookSettings(token, bookId, {
        target_language: form.target_language,
        model_source: form.model_source,
        model_ref: form.model_ref,
        system_prompt: form.system_prompt,
        user_prompt_tpl: form.user_prompt_tpl,
      });
      setSettings(saved);
      setSaveSuccess('Book translation settings saved');
    } catch (e: unknown) {
      setSaveError((e as { message?: string })?.message || 'Failed to save');
    } finally {
      setSaving(false);
    }
  }

  async function handleResetToDefaults() {
    const prefs = await translationApi.getPreferences(token);
    setForm(settingsToForm({ ...prefs, book_id: bookId!, owner_user_id: prefs.user_id, is_default: true }));
  }

  function handleJobCreated(job: TranslationJob) {
    setJobs((prev) => [job, ...prev]);
  }

  return (
    <div className="space-y-6">
      {/* Section 1 — Settings */}
      <section className="space-y-4 rounded border p-4">
        <h2 className="font-medium">Translation settings for this book</h2>

        {loadingSettings ? (
          <div className="space-y-3">
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-32 w-full" />
          </div>
        ) : (
          <>
            {settings?.is_default && (
              <Alert>
                <AlertDescription>
                  Using your default settings. Save below to override for this book.
                </AlertDescription>
              </Alert>
            )}
            {form && (
              <div className="space-y-4">
                <LanguagePicker
                  label="Target language"
                  value={form.target_language}
                  onChange={(v) => setForm({ ...form, target_language: v })}
                />
                <ModelSelector
                  token={token}
                  value={{ model_source: form.model_source, model_ref: form.model_ref }}
                  onChange={(v) => setForm({ ...form, model_source: v.model_source, model_ref: v.model_ref })}
                  disabled={saving}
                />
                <PromptEditor
                  systemPrompt={form.system_prompt}
                  userPromptTpl={form.user_prompt_tpl}
                  onSystemPromptChange={(v) => setForm({ ...form, system_prompt: v })}
                  onUserPromptTplChange={(v) => setForm({ ...form, user_prompt_tpl: v })}
                  disabled={saving}
                />
                {saveError && <Alert variant="destructive"><AlertDescription>{saveError}</AlertDescription></Alert>}
                {saveSuccess && <p className="text-sm text-green-600">{saveSuccess}</p>}
                <div className="flex gap-2">
                  <Button onClick={handleSave} disabled={saving}>
                    {saving ? 'Saving…' : 'Save for this book'}
                  </Button>
                  <Button variant="outline" onClick={handleResetToDefaults} disabled={saving}>
                    Reset to my defaults
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </section>

      {/* Section 2 — Translate */}
      <section className="space-y-4 rounded border p-4">
        <h2 className="font-medium">Translate chapters</h2>

        {loadingChapters ? (
          <div className="space-y-2">
            <Skeleton className="h-5 w-full" />
            <Skeleton className="h-5 w-full" />
            <Skeleton className="h-5 w-2/3" />
          </div>
        ) : (
          <>
            <div className="flex gap-2">
              <button
                className="text-sm underline"
                onClick={() => setSelectedIds(chapters.map((c) => c.chapter_id))}
              >
                Select all
              </button>
              <button
                className="text-sm underline"
                onClick={() => setSelectedIds([])}
              >
                Deselect all
              </button>
            </div>
            <div className="space-y-1">
              {chapters.map((c) => (
                <label key={c.chapter_id} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={selectedIds.includes(c.chapter_id)}
                    onChange={() => toggleChapter(c.chapter_id)}
                  />
                  {c.title || `Chapter ${c.sort_order}`}
                </label>
              ))}
            </div>
          </>
        )}

        {!loadingSettings && !loadingChapters && bookId && (
          <TranslateButton
            token={token}
            bookId={bookId}
            chapterIds={selectedIds}
            onJobCreated={handleJobCreated}
            disabled={!form?.model_ref}
          />
        )}
        {!form?.model_ref && !loadingSettings && (
          <p className="text-sm text-amber-600">
            No model configured — go to{' '}
            <a href="/settings/translation" className="underline">Translation Settings</a>
            {' '}to set a default model.
          </p>
        )}
      </section>

      {/* Section 3 — Recent jobs */}
      <section className="space-y-3 rounded border p-4">
        <h2 className="font-medium">Recent translation jobs</h2>

        {loadingJobs ? (
          <div className="space-y-2">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
          </div>
        ) : jobs.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No translation jobs yet. Click Translate above to get started.
          </p>
        ) : (
          <div className="space-y-2">
            {jobs.map((job) => (
              <details key={job.job_id} className="rounded border">
                <summary className="flex cursor-pointer items-center gap-2 px-3 py-2 text-sm">
                  <StatusBadge status={job.status} />
                  <span>{new Date(job.created_at).toLocaleDateString()}</span>
                  <span className="text-muted-foreground">
                    {job.completed_chapters}/{job.total_chapters} → {job.target_language}
                  </span>
                </summary>
                <div className="space-y-2 px-3 pb-3">
                  {job.chapter_ids.map((cid) => {
                    const chapter = chapters.find((c) => c.chapter_id === cid);
                    return (
                      <ChapterTranslationPanel
                        key={cid}
                        token={token}
                        jobId={job.job_id}
                        chapterId={cid}
                        chapterTitle={chapter?.title || `Chapter ${chapter?.sort_order ?? ''}`}
                      />
                    );
                  })}
                </div>
              </details>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    completed: '✓',
    partial: '⚠',
    failed: '✗',
    running: '◌',
    pending: '◌',
    cancelled: '—',
  };
  const colorMap: Record<string, string> = {
    completed: 'text-green-600',
    partial: 'text-amber-600',
    failed: 'text-red-600',
    cancelled: 'text-muted-foreground',
  };
  return (
    <span className={colorMap[status] || 'text-muted-foreground'}>
      {map[status] || status}
    </span>
  );
}
