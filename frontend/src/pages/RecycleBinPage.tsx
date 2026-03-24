import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '@/auth';
import { booksApi, type Book } from '@/features/books/api';
import { glossaryApi } from '@/features/glossary/api';
import type { EntityTrashItem } from '@/features/glossary/types';

type Tab = 'books' | 'glossary';

export function RecycleBinPage() {
  const { accessToken } = useAuth();
  const [tab, setTab] = useState<Tab>('books');

  // ── Books tab ──────────────────────────────────────────────────────────────
  const [bookItems, setBookItems] = useState<Book[]>([]);
  const [bookError, setBookError] = useState('');

  const loadBooks = async () => {
    if (!accessToken) return;
    try {
      const res = await booksApi.listTrash(accessToken);
      setBookItems(res.items);
      setBookError('');
    } catch (e) {
      setBookError((e as Error).message);
    }
  };

  // ── Glossary tab ───────────────────────────────────────────────────────────
  const [glossaryItems, setGlossaryItems] = useState<EntityTrashItem[]>([]);
  const [glossaryError, setGlossaryError] = useState('');
  const [glossaryLoading, setGlossaryLoading] = useState(false);

  const loadGlossary = async () => {
    if (!accessToken) return;
    setGlossaryLoading(true);
    setGlossaryError('');
    try {
      const booksRes = await booksApi.listBooks(accessToken);
      const results = await Promise.all(
        booksRes.items.map((b) =>
          glossaryApi
            .listEntityTrash(b.book_id, accessToken, { limit: 100 })
            .then((r) => r.items)
            .catch(() => [] as EntityTrashItem[]),
        ),
      );
      setGlossaryItems(
        results.flat().sort(
          (a, b) => new Date(b.deleted_at).getTime() - new Date(a.deleted_at).getTime(),
        ),
      );
    } catch (e) {
      setGlossaryError((e as Error).message);
    } finally {
      setGlossaryLoading(false);
    }
  };

  useEffect(() => { void loadBooks(); }, [accessToken]);

  useEffect(() => {
    if (tab === 'glossary') void loadGlossary();
  }, [tab, accessToken]);

  // ── Actions ────────────────────────────────────────────────────────────────
  const restoreBook = async (bookId: string) => {
    if (!accessToken) return;
    await booksApi.restoreBook(accessToken, bookId);
    void loadBooks();
  };
  const purgeBook = async (bookId: string) => {
    if (!accessToken) return;
    await booksApi.purgeBook(accessToken, bookId);
    void loadBooks();
  };
  const restoreEntity = async (item: EntityTrashItem) => {
    if (!accessToken) return;
    await glossaryApi.restoreEntity(item.book_id, item.entity_id, accessToken);
    void loadGlossary();
  };
  const purgeEntity = async (item: EntityTrashItem) => {
    if (!accessToken) return;
    await glossaryApi.purgeEntity(item.book_id, item.entity_id, accessToken);
    void loadGlossary();
  };

  const tabClass = (t: Tab) =>
    `px-3 py-1.5 text-sm font-medium rounded-t border-b-2 transition-colors ${
      tab === t
        ? 'border-foreground text-foreground'
        : 'border-transparent text-muted-foreground hover:text-foreground'
    }`;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Recycle bin</h1>
        <Link to="/books" className="text-sm underline">Back to books</Link>
      </div>

      {/* Category tabs */}
      <div className="flex gap-1 border-b">
        <button className={tabClass('books')} onClick={() => setTab('books')}>
          Books
        </button>
        <button className={tabClass('glossary')} onClick={() => setTab('glossary')}>
          Glossary Entities
        </button>
      </div>

      {/* Books tab */}
      {tab === 'books' && (
        <>
          {bookError && <p className="text-sm text-destructive">{bookError}</p>}
          <ul className="space-y-2">
            {bookItems.map((b) => (
              <li key={b.book_id} className="rounded border p-3 text-sm">
                <p className="font-medium">{b.title}</p>
                <div className="mt-2 flex gap-3">
                  <button className="underline" onClick={() => void restoreBook(b.book_id)}>
                    Restore
                  </button>
                  <button
                    className="underline text-destructive"
                    onClick={() => void purgeBook(b.book_id)}
                  >
                    Delete permanently
                  </button>
                </div>
              </li>
            ))}
            {bookItems.length === 0 && (
              <p className="text-sm text-muted-foreground">No books in trash.</p>
            )}
          </ul>
        </>
      )}

      {/* Glossary tab */}
      {tab === 'glossary' && (
        <>
          {glossaryError && <p className="text-sm text-destructive">{glossaryError}</p>}
          {glossaryLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
          <ul className="space-y-2">
            {glossaryItems.map((it) => (
              <li key={it.entity_id} className="rounded border p-3 text-sm">
                <div className="flex items-center gap-2">
                  <span
                    className="h-2.5 w-2.5 shrink-0 rounded-full"
                    style={{ background: it.kind_color }}
                  />
                  <p className="font-medium">{it.display_name || '(unnamed)'}</p>
                  <span className="ml-1 text-xs text-muted-foreground">{it.kind_name}</span>
                </div>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  Deleted {new Date(it.deleted_at).toLocaleDateString()}
                </p>
                <div className="mt-2 flex gap-3">
                  <button className="underline text-sm" onClick={() => void restoreEntity(it)}>
                    Restore
                  </button>
                  <button
                    className="underline text-sm text-destructive"
                    onClick={() => void purgeEntity(it)}
                  >
                    Delete permanently
                  </button>
                </div>
              </li>
            ))}
            {!glossaryLoading && glossaryItems.length === 0 && (
              <p className="text-sm text-muted-foreground">No glossary entities in trash.</p>
            )}
          </ul>
        </>
      )}
    </div>
  );
}
