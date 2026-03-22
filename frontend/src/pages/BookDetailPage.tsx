import { FormEvent, useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '@/auth';
import { booksApi, type Book, type Chapter } from '@/features/books/api';
import { LanguagePicker } from '@/components/books/LanguagePicker';
import { PaginationBar } from '@/components/books/PaginationBar';
import { VisibilityBadge } from '@/components/books/VisibilityBadge';
import { LanguageStatusDots } from '@/components/translation/LanguageStatusDots';
import { versionsApi, type ChapterCoverage } from '@/features/translation/versionsApi';

export function BookDetailPage() {
  const { accessToken } = useAuth();
  const navigate = useNavigate();
  const { bookId = '' } = useParams();
  const [book, setBook] = useState<Book | null>(null);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [total, setTotal] = useState(0);
  const [limit] = useState(10);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState('');
  const [langFilter, setLangFilter] = useState('');
  const [sortOrderFilter, setSortOrderFilter] = useState('');
  const [lifecycleFilter, setLifecycleFilter] = useState('active');
  const [newTitle, setNewTitle] = useState('');
  const [newLang, setNewLang] = useState('');
  const [newFile, setNewFile] = useState<File | null>(null);
  const [editorBody, setEditorBody] = useState('');
  const [downloadBusy, setDownloadBusy] = useState<string | null>(null);
  const [coverage, setCoverage] = useState<ChapterCoverage[]>([]);

  const load = async () => {
    if (!accessToken || !bookId) return;
    try {
      const b = await booksApi.getBook(accessToken, bookId);
      setBook(b);
      const ch = await booksApi.listChapters(accessToken, bookId, {
        original_language: langFilter || undefined,
        sort_order: sortOrderFilter ? Number(sortOrderFilter) : undefined,
        lifecycle_state: lifecycleFilter || undefined,
        limit,
        offset,
      });
      setChapters(ch.items);
      setTotal(ch.total);
      setError('');
      // Load translation coverage (best-effort — don't block chapter list on failure)
      versionsApi.getBookCoverage(accessToken!, bookId).then((r) => setCoverage(r.coverage)).catch(() => {});
    } catch (e) {
      setError((e as Error).message);
    }
  };

  useEffect(() => {
    void load();
  }, [accessToken, bookId, langFilter, sortOrderFilter, lifecycleFilter, limit, offset]);

  const uploadChapter = async (e: FormEvent) => {
    e.preventDefault();
    if (!accessToken || !bookId || !newFile || !newLang) return;
    try {
      await booksApi.createChapterUpload(accessToken, bookId, {
        file: newFile,
        original_language: newLang,
        title: newTitle || undefined,
      });
      setNewFile(null);
      setNewLang('');
      setNewTitle('');
      setOffset(0);
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const createFromEditor = async (e: FormEvent) => {
    e.preventDefault();
    if (!accessToken || !bookId || !newLang) return;
    try {
      const created = await booksApi.createChapterEditor(accessToken, bookId, {
        title: newTitle || undefined,
        original_language: newLang,
        body: editorBody || undefined,
      });
      navigate(`/books/${bookId}/chapters/${created.chapter_id}/edit`);
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const trashChapter = async (chapterId: string) => {
    if (!accessToken || !bookId) return;
    await booksApi.trashChapter(accessToken, bookId, chapterId);
    await load();
  };

  const trashBook = async () => {
    if (!accessToken || !bookId) return;
    await booksApi.trashBook(accessToken, bookId);
    await load();
  };

  const downloadRaw = async (chapterId: string) => {
    if (!accessToken || !bookId) return;
    setDownloadBusy(chapterId);
    try {
      const blob = await booksApi.downloadRaw(accessToken, bookId, chapterId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `chapter-${chapterId}.txt`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setDownloadBusy(null);
    }
  };

  if (!book) return <p className="text-sm text-muted-foreground">{error || 'Loading...'}</p>;

  return (
    <div className="space-y-5">
      <div className="space-y-1">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-semibold">{book.title}</h1>
          <VisibilityBadge visibility={book.visibility} />
        </div>
        <p className="text-xs text-muted-foreground">state: {book.lifecycle_state} | language: {book.original_language || 'n/a'}</p>
        <div className="flex flex-wrap gap-3 text-sm">
          <Link to={`/books/${bookId}/sharing`} className="underline">
            Sharing
          </Link>
          <Link to={`/books/${bookId}/translation`} className="underline">
            Translation
          </Link>
          <button onClick={() => void trashBook()} className="underline">
            Move book to trash
          </button>
        </div>
      </div>

      <div className="grid gap-5 xl:grid-cols-2">
        <div className="space-y-2 rounded border p-4">
          <h2 className="font-medium">Create chapter in editor</h2>
          <form className="space-y-2" onSubmit={createFromEditor}>
            <input
              className="w-full rounded border px-2 py-2"
              placeholder="Chapter title"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
            />
            <LanguagePicker value={newLang} onChange={setNewLang} label="Original language" required />
            <textarea
              className="min-h-[140px] w-full rounded border px-2 py-2 text-sm"
              placeholder="Initial draft (optional)"
              value={editorBody}
              onChange={(e) => setEditorBody(e.target.value)}
            />
            <button className="rounded bg-primary px-3 py-1.5 text-primary-foreground">Create in editor</button>
          </form>
        </div>

        <div className="space-y-2 rounded border p-4">
          <h2 className="font-medium">Upload chapter (.txt)</h2>
          <form className="space-y-2" onSubmit={uploadChapter}>
            <input
              className="w-full rounded border px-2 py-2"
              placeholder="Chapter title"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
            />
            <LanguagePicker value={newLang} onChange={setNewLang} label="Original language" required />
            <input
              className="w-full rounded border px-2 py-2"
              type="file"
              accept=".txt,text/plain"
              onChange={(e) => setNewFile(e.target.files?.[0] ?? null)}
              required
            />
            <button className="rounded bg-primary px-3 py-1.5 text-primary-foreground">Upload file</button>
          </form>
        </div>
      </div>

      <div className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-medium">Chapters</h2>
          <div className="grid w-full gap-2 sm:grid-cols-3 lg:w-auto">
            <input
              className="rounded border px-2 py-1 text-sm"
              placeholder="Filter language"
              value={langFilter}
              onChange={(e) => {
                setOffset(0);
                setLangFilter(e.target.value);
              }}
            />
            <input
              className="rounded border px-2 py-1 text-sm"
              placeholder="Sort order"
              value={sortOrderFilter}
              onChange={(e) => {
                setOffset(0);
                setSortOrderFilter(e.target.value);
              }}
            />
            <select
              className="rounded border px-2 py-1 text-sm"
              value={lifecycleFilter}
              onChange={(e) => {
                setOffset(0);
                setLifecycleFilter(e.target.value);
              }}
            >
              <option value="active">active</option>
              <option value="trashed">trashed</option>
              <option value="purge_pending">purge_pending</option>
            </select>
          </div>
        </div>
        <ul className="space-y-2">
          {chapters.map((c) => {
            const chapterCoverage = coverage.find((cv) => cv.chapter_id === c.chapter_id);
            return (
              <li key={c.chapter_id} className="rounded border p-3 text-sm">
                <div className="flex items-start justify-between gap-2">
                  <p className="font-medium">{c.title || c.original_filename}</p>
                  {chapterCoverage && (
                    <LanguageStatusDots
                      bookId={bookId}
                      chapterId={c.chapter_id}
                      coverage={chapterCoverage.languages}
                    />
                  )}
                </div>
                <p className="text-xs text-muted-foreground">
                  order={c.sort_order} | lang={c.original_language} | state={c.lifecycle_state}
                </p>
                <div className="mt-2 flex flex-wrap gap-3">
                  <Link to={`/books/${bookId}/chapters/${c.chapter_id}/edit`} className="underline">
                    Edit draft
                  </Link>
                  <Link to={`/books/${bookId}/chapters/${c.chapter_id}/translations`} className="underline">
                    Translations
                  </Link>
                  <button className="underline" onClick={() => void downloadRaw(c.chapter_id)} disabled={downloadBusy === c.chapter_id}>
                    {downloadBusy === c.chapter_id ? 'Downloading…' : 'Download raw'}
                  </button>
                  <button className="underline" onClick={() => void trashChapter(c.chapter_id)}>
                    Trash
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
        <PaginationBar total={total} limit={limit} offset={offset} onChange={setOffset} />
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
    </div>
  );
}
