import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '@/auth';
import { booksApi, type Book } from '@/features/books/api';

export function RecycleBinPage() {
  const { accessToken } = useAuth();
  const [items, setItems] = useState<Book[]>([]);
  const [error, setError] = useState('');

  const load = async () => {
    if (!accessToken) return;
    try {
      const res = await booksApi.listTrash(accessToken);
      setItems(res.items);
      setError('');
    } catch (e) {
      setError((e as Error).message);
    }
  };

  useEffect(() => {
    void load();
  }, [accessToken]);

  const restore = async (bookId: string) => {
    if (!accessToken) return;
    await booksApi.restoreBook(accessToken, bookId);
    await load();
  };
  const purge = async (bookId: string) => {
    if (!accessToken) return;
    await booksApi.purgeBook(accessToken, bookId);
    await load();
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Recycle bin</h1>
        <Link to="/books" className="text-sm underline">
          Back to books
        </Link>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <ul className="space-y-2">
        {items.map((b) => (
          <li key={b.book_id} className="rounded border p-3 text-sm">
            <p className="font-medium">{b.title}</p>
            <div className="mt-2 flex gap-3">
              <button className="underline" onClick={() => void restore(b.book_id)}>
                Restore
              </button>
              <button className="underline" onClick={() => void purge(b.book_id)}>
                Delete permanently
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
