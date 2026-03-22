import { useCallback, useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useAuth } from '@/auth';
import { useJobEvents, type JobEvent } from '@/hooks/useJobEvents';
import { Skeleton } from '@/components/ui/skeleton';
import { TranslationMatrix } from '@/components/translation/TranslationMatrix';
import { FloatingActionBar } from '@/components/translation/FloatingActionBar';
import { TranslateModal } from '@/components/translation/TranslateModal';
import { SettingsDrawer } from '@/components/translation/SettingsDrawer';
import { JobsDrawer } from '@/components/translation/JobsDrawer';
import { translationApi, type BookTranslationSettings, type TranslationJob } from '@/features/translation/api';
import { versionsApi, type ChapterCoverage, type BookCoverageResponse } from '@/features/translation/versionsApi';
import { booksApi, type Chapter } from '@/features/books/api';

export default function BookTranslationPage() {
  const { bookId } = useParams<{ bookId: string }>();
  const { accessToken } = useAuth();
  const token = accessToken!;

  const [loading, setLoading] = useState(true);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [settings, setSettings] = useState<BookTranslationSettings | null>(null);
  const [jobs, setJobs] = useState<TranslationJob[]>([]);
  const [coverageData, setCoverageData] = useState<BookCoverageResponse | null>(null);

  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [langFilter, setLangFilter] = useState('');
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [jobsOpen, setJobsOpen] = useState(false);
  const [translateOpen, setTranslateOpen] = useState(false);

  const preselectedRef = useRef(false);

  const loadAll = useCallback(async () => {
    if (!bookId) return;
    setLoading(true);
    try {
      const [chaptersResp, settingsResp, jobsResp, coverageResp] = await Promise.all([
        booksApi.listChapters(token, bookId, { lifecycle_state: 'active', limit: 100 }),
        translationApi.getBookSettings(token, bookId),
        translationApi.listJobs(token, bookId, { limit: 10 }),
        versionsApi.getBookCoverage(token, bookId),
      ]);
      setChapters(chaptersResp.items);
      setSettings(settingsResp);
      setJobs(jobsResp);
      setCoverageData(coverageResp);
    } finally {
      setLoading(false);
    }
  }, [token, bookId]);

  useEffect(() => { void loadAll(); }, [loadAll]);

  // Pre-select untranslated chapters — one-shot after load
  useEffect(() => {
    if (loading || preselectedRef.current || coverageData === null) return;
    preselectedRef.current = true;

    const coveredIds = new Set(
      coverageData.coverage
        .filter((c) => Object.values(c.languages).some((cell) => cell?.has_active))
        .map((c) => c.chapter_id)
    );
    const untranslated = chapters
      .filter((c) => !coveredIds.has(c.chapter_id))
      .map((c) => c.chapter_id);
    setSelectedIds(untranslated.length > 0 ? untranslated : chapters.map((c) => c.chapter_id));
  }, [loading, coverageData, chapters]);

  // WebSocket live-update
  const handleJobEvent = useCallback((e: JobEvent) => {
    if (e.job_type !== 'translation') return;
    if (e.event === 'job.status_changed' || e.event === 'job.chapter_done') {
      setJobs((prev) =>
        prev.map((j) =>
          j.job_id === e.job_id ? { ...j, ...(e.payload as Partial<TranslationJob>) } : j
        )
      );
      // Refresh coverage on chapter completion
      if (e.event === 'job.chapter_done' && bookId) {
        versionsApi.getBookCoverage(token, bookId).then(setCoverageData).catch(() => {});
      }
    }
    if (e.event === 'job.created' && bookId) {
      translationApi.listJobs(token, bookId, { limit: 10 }).then(setJobs).catch(() => {});
    }
  }, [token, bookId]);

  const handleReconnect = useCallback(() => {
    if (bookId) {
      void Promise.all([
        translationApi.listJobs(token, bookId, { limit: 10 }).then(setJobs),
        versionsApi.getBookCoverage(token, bookId).then(setCoverageData),
      ]);
    }
  }, [token, bookId]);

  useJobEvents({ onEvent: handleJobEvent, onReconnect: handleReconnect });

  function handleJobCreated(job: TranslationJob) {
    setJobs((prev) => [job, ...prev]);
    setTranslateOpen(false);
    setSelectedIds([]);
  }

  const runningCount = jobs.filter((j) => j.status === 'pending' || j.status === 'running').length;

  return (
    <div className="space-y-4">
      {/* Page header */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-lg font-semibold">Translation Dashboard</h1>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setJobsOpen(true)}
            className="rounded border px-3 py-1.5 text-sm hover:bg-muted"
          >
            Jobs {runningCount > 0 && <span className="ml-1 text-amber-600">({runningCount} active)</span>}
          </button>
          <button
            onClick={() => setSettingsOpen(true)}
            className="rounded border px-3 py-1.5 text-sm hover:bg-muted"
          >
            ⚙ Settings
          </button>
        </div>
      </div>

      {/* Translation matrix */}
      <div className="rounded border">
        {!loading && (coverageData?.known_languages?.length ?? 0) > 0 && (
          <div className="flex items-center gap-2 border-b px-3 py-2">
            <label className="text-xs text-muted-foreground">Filter language:</label>
            <select
              className="rounded border px-2 py-1 text-xs"
              value={langFilter}
              onChange={(e) => setLangFilter(e.target.value)}
            >
              <option value="">All</option>
              {(coverageData?.known_languages ?? []).map((lang) => (
                <option key={lang} value={lang}>{lang}</option>
              ))}
            </select>
            {langFilter && (
              <button
                className="text-xs text-muted-foreground hover:underline"
                onClick={() => setLangFilter('')}
              >
                Clear
              </button>
            )}
          </div>
        )}
        {loading ? (
          <div className="space-y-2 p-4">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-3/4" />
          </div>
        ) : (
          <TranslationMatrix
            bookId={bookId!}
            chapters={chapters}
            coverage={coverageData?.coverage ?? []}
            knownLanguages={langFilter ? [langFilter] : (coverageData?.known_languages ?? [])}
            selectedIds={selectedIds}
            onToggle={(id) =>
              setSelectedIds((prev) =>
                prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
              )
            }
            onSelectAll={() => setSelectedIds(chapters.map((c) => c.chapter_id))}
            onDeselectAll={() => setSelectedIds([])}
          />
        )}
      </div>

      {/* Floating action bar */}
      <FloatingActionBar
        selectedCount={selectedIds.length}
        onTranslate={() => setTranslateOpen(true)}
        onClear={() => setSelectedIds([])}
      />

      {/* Drawers & modals */}
      {settingsOpen && settings && (
        <SettingsDrawer
          token={token}
          bookId={bookId!}
          settings={settings}
          onClose={() => setSettingsOpen(false)}
          onSaved={(updated) => { setSettings(updated); setSettingsOpen(false); }}
        />
      )}

      {jobsOpen && (
        <JobsDrawer
          token={token}
          bookId={bookId!}
          jobs={jobs}
          onClose={() => setJobsOpen(false)}
          onJobsChange={setJobs}
        />
      )}

      {translateOpen && settings && (
        <TranslateModal
          token={token}
          bookId={bookId!}
          chapterIds={selectedIds}
          settings={settings}
          onClose={() => setTranslateOpen(false)}
          onJobCreated={handleJobCreated}
        />
      )}
    </div>
  );
}
