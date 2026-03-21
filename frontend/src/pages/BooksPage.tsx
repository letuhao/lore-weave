import { FormEvent, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '@/auth';
import { m02Api, type Book } from '@/m02/api';
import { LanguagePicker } from '@/components/m02/LanguagePicker';
import { PaginationBar } from '@/components/m02/PaginationBar';
import { VisibilityBadge } from '@/components/m02/VisibilityBadge';

export function BooksPage() {
  const { accessToken } = useAuth();
  const [items, setItems] = useState<Book[]>([]);
  const [total, setTotal] = useState(0);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [originalLanguage, setOriginalLanguage] = useState('');
  const [coverFile, setCoverFile] = useState<File | null>(null);
  const [error, setError] = useState('');

  const load = async () => {
    if (!accessToken) return;
    try {
      const res = await m02Api.listBooks(accessToken);
      setItems(res.items);
      setTotal(res.total || res.items.length);
      setError('');
    } catch (e) {
      setError((e as Error).message);
    }
  };

  useEffect(() => {
    void load();
  }, [accessToken]);

  const onCreate = async (e: FormEvent) => {
    e.preventDefault();
    if (!accessToken) return;
    try {
      const created = await m02Api.createBook(accessToken, {
        title,
        description: description || undefined,
        original_language: originalLanguage || undefined,
      });
      if (coverFile) {
        await m02Api.uploadCover(accessToken, created.book_id, coverFile);
      }
      setTitle('');
      setDescription('');
      setOriginalLanguage('');
      setCoverFile(null);
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">My books</h1>
        <Link to="/books/trash" className="text-sm underline">
          Recycle bin
        </Link>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="grid gap-5 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)]">
        <form onSubmit={onCreate} className="space-y-3 rounded border p-4">
          <h2 className="font-medium">Create book</h2>
          <input
            className="w-full rounded border px-2 py-2"
            placeholder="Title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
          />
          <textarea
            className="min-h-[90px] w-full rounded border px-2 py-2 text-sm"
            placeholder="Description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
          <LanguagePicker value={originalLanguage} onChange={setOriginalLanguage} label="Original language" />
          <div className="space-y-2">
            <label className="text-sm font-medium">Cover image</label>
            <input
              className="w-full rounded border px-2 py-2 text-sm"
              type="file"
              accept="image/*"
              onChange={(e) => setCoverFile(e.target.files?.[0] ?? null)}
            />
          </div>
          <button className="rounded bg-primary px-3 py-1.5 text-primary-foreground">Create</button>
        </form>

        <div className="space-y-3 rounded border p-4">
          <h2 className="font-medium">Book list</h2>
          <ul className="space-y-2">
            {items.map((b) => (
              <li key={b.book_id} className="rounded border p-3">
                <div className="flex items-start justify-between gap-3">
                  <Link to={`/books/${b.book_id}`} className="font-medium underline">
                    {b.title}
                  </Link>
                  <VisibilityBadge visibility={b.visibility} />
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  language: {b.original_language || 'n/a'} | chapters: {b.chapter_count} | state: {b.lifecycle_state}
                </p>
              </li>
            ))}
          </ul>
          <PaginationBar total={total} limit={Math.max(total || 1, 1)} offset={0} onChange={() => undefined} />
        </div>
      </div>
    </div>
  );
}
