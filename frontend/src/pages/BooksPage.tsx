import { FormEvent, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '@/auth';
import { m02Api, type Book } from '@/m02/api';

export function BooksPage() {
  const { accessToken } = useAuth();
  const [items, setItems] = useState<Book[]>([]);
  const [title, setTitle] = useState('');
  const [originalLanguage, setOriginalLanguage] = useState('');
  const [error, setError] = useState('');

  const load = async () => {
    if (!accessToken) return;
    try {
      const res = await m02Api.listBooks(accessToken);
      setItems(res.items);
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
      await m02Api.createBook(accessToken, {
        title,
        original_language: originalLanguage || undefined,
      });
      setTitle('');
      setOriginalLanguage('');
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">My books</h1>
        <Link to="/books/trash" className="text-sm underline">
          Recycle bin
        </Link>
      </div>

      <form onSubmit={onCreate} className="space-y-2 rounded border p-3">
        <h2 className="font-medium">Create book</h2>
        <input
          className="w-full rounded border px-2 py-1"
          placeholder="Title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          required
        />
        <input
          className="w-full rounded border px-2 py-1"
          placeholder="Original language (e.g. en)"
          value={originalLanguage}
          onChange={(e) => setOriginalLanguage(e.target.value)}
        />
        <button className="rounded bg-primary px-3 py-1 text-primary-foreground">Create</button>
      </form>

      {error && <p className="text-sm text-red-600">{error}</p>}
      <ul className="space-y-2">
        {items.map((b) => (
          <li key={b.book_id} className="rounded border p-3">
            <Link to={`/books/${b.book_id}`} className="font-medium underline">
              {b.title}
            </Link>
            <p className="text-xs text-muted-foreground">
              language: {b.original_language || 'n/a'} | chapters: {b.chapter_count}
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
}
