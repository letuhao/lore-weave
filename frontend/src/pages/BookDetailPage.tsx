import { FormEvent, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useAuth } from '@/auth';
import { m02Api, type Book, type Chapter } from '@/m02/api';

export function BookDetailPage() {
  const { accessToken } = useAuth();
  const { bookId = '' } = useParams();
  const [book, setBook] = useState<Book | null>(null);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [error, setError] = useState('');
  const [langFilter, setLangFilter] = useState('');
  const [newTitle, setNewTitle] = useState('');
  const [newLang, setNewLang] = useState('');
  const [newFile, setNewFile] = useState<File | null>(null);

  const load = async () => {
    if (!accessToken || !bookId) return;
    try {
      const b = await m02Api.getBook(accessToken, bookId);
      setBook(b);
      const query = langFilter ? `?original_language=${encodeURIComponent(langFilter)}` : '';
      const ch = await m02Api.listChapters(accessToken, bookId, query);
      setChapters(ch.items);
      setError('');
    } catch (e) {
      setError((e as Error).message);
    }
  };

  useEffect(() => {
    void load();
  }, [accessToken, bookId, langFilter]);

  const uploadChapter = async (e: FormEvent) => {
    e.preventDefault();
    if (!accessToken || !bookId || !newFile || !newLang) return;
    try {
      await m02Api.createChapter(accessToken, bookId, {
        file: newFile,
        original_language: newLang,
        title: newTitle || undefined,
      });
      setNewFile(null);
      setNewLang('');
      setNewTitle('');
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const trashChapter = async (chapterId: string) => {
    if (!accessToken || !bookId) return;
    await m02Api.trashChapter(accessToken, bookId, chapterId);
    await load();
  };

  const trashBook = async () => {
    if (!accessToken || !bookId) return;
    await m02Api.trashBook(accessToken, bookId);
    await load();
  };

  if (!book) return <p className="text-sm text-muted-foreground">{error || 'Loading...'}</p>;

  return (
    <div className="space-y-4">
      <div className="space-y-1">
        <h1 className="text-xl font-semibold">{book.title}</h1>
        <p className="text-xs text-muted-foreground">
          state: {book.lifecycle_state} | language: {book.original_language || 'n/a'}
        </p>
        <div className="flex gap-3 text-sm">
          <Link to={`/books/${bookId}/sharing`} className="underline">
            Sharing
          </Link>
          <button onClick={() => void trashBook()} className="underline">
            Move book to trash
          </button>
        </div>
      </div>

      <div className="space-y-2 rounded border p-3">
        <h2 className="font-medium">Add chapter</h2>
        <form className="space-y-2" onSubmit={uploadChapter}>
          <input
            className="w-full rounded border px-2 py-1"
            placeholder="Chapter title"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
          />
          <input
            className="w-full rounded border px-2 py-1"
            placeholder="Language (required)"
            value={newLang}
            onChange={(e) => setNewLang(e.target.value)}
            required
          />
          <input
            type="file"
            accept=".txt,text/plain"
            onChange={(e) => setNewFile(e.target.files?.[0] ?? null)}
            required
          />
          <button className="rounded bg-primary px-3 py-1 text-primary-foreground">Upload</button>
        </form>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="font-medium">Chapters</h2>
          <input
            className="rounded border px-2 py-1 text-sm"
            placeholder="Filter language"
            value={langFilter}
            onChange={(e) => setLangFilter(e.target.value)}
          />
        </div>
        <ul className="space-y-2">
          {chapters.map((c) => (
            <li key={c.chapter_id} className="rounded border p-3 text-sm">
              <p className="font-medium">{c.title || c.original_filename}</p>
              <p className="text-xs text-muted-foreground">
                order={c.sort_order} | lang={c.original_language} | state={c.lifecycle_state}
              </p>
              <div className="mt-2 flex gap-3">
                <Link to={`/books/${bookId}/chapters/${c.chapter_id}/edit`} className="underline">
                  Edit draft
                </Link>
                <a
                  href={`${import.meta.env.VITE_API_BASE || 'http://localhost:3000'}/v1/books/${bookId}/chapters/${c.chapter_id}/content`}
                  target="_blank"
                  rel="noreferrer"
                  className="underline"
                >
                  Download raw
                </a>
                <button className="underline" onClick={() => void trashChapter(c.chapter_id)}>
                  Trash
                </button>
              </div>
            </li>
          ))}
        </ul>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
    </div>
  );
}
