import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@/auth';
import { booksApi, type Book } from '@/features/books/api';
import { glossaryApi } from '@/features/glossary/api';
import type { EntityTrashItem } from '@/features/glossary/types';
import { bookToTrashItem, glossaryToTrashItem, type TrashItem, type TrashType } from './types';

interface UseTrashItemsReturn {
  items: TrashItem[];
  counts: Record<TrashType, number>;
  isLoading: boolean;
  refresh: () => Promise<void>;
  restoreBook: (bookId: string) => Promise<void>;
  purgeBook: (bookId: string) => Promise<void>;
  restoreGlossary: (item: EntityTrashItem) => Promise<void>;
  purgeGlossary: (item: EntityTrashItem) => Promise<void>;
}

export function useTrashItems(): UseTrashItemsReturn {
  const { accessToken } = useAuth();
  const [bookItems, setBookItems] = useState<TrashItem[]>([]);
  const [glossaryItems, setGlossaryItems] = useState<TrashItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  // ── Fetch books ───────────────────────────────────────────────────────────

  const fetchBooks = useCallback(async () => {
    if (!accessToken) return;
    try {
      const res = await booksApi.listTrash(accessToken);
      setBookItems(res.items.map(bookToTrashItem));
    } catch {
      setBookItems([]);
    }
  }, [accessToken]);

  // ── Fetch glossary (across all books) ─────────────────────────────────────

  const fetchGlossary = useCallback(async () => {
    if (!accessToken) return;
    try {
      // Get all books to scan their glossary trash
      const booksRes = await booksApi.listBooks(accessToken);
      const bookMap = new Map(booksRes.items.map((b) => [b.book_id, b.title]));

      const results = await Promise.all(
        booksRes.items.map((b) =>
          glossaryApi
            .listEntityTrash(b.book_id, accessToken, { limit: 100 })
            .then((r) => r.items.map((it) => glossaryToTrashItem(it, bookMap.get(b.book_id))))
            .catch(() => [] as TrashItem[]),
        ),
      );

      setGlossaryItems(
        results.flat().sort((a, b) => new Date(b.deletedAt).getTime() - new Date(a.deletedAt).getTime()),
      );
    } catch {
      setGlossaryItems([]);
    }
  }, [accessToken]);

  // ── Combined refresh ──────────────────────────────────────────────────────

  const refresh = useCallback(async () => {
    setIsLoading(true);
    await Promise.all([fetchBooks(), fetchGlossary()]);
    setIsLoading(false);
  }, [fetchBooks, fetchGlossary]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // ── Actions ───────────────────────────────────────────────────────────────

  const restoreBook = useCallback(
    async (bookId: string) => {
      if (!accessToken) return;
      await booksApi.restoreBook(accessToken, bookId);
      await fetchBooks();
    },
    [accessToken, fetchBooks],
  );

  const purgeBook = useCallback(
    async (bookId: string) => {
      if (!accessToken) return;
      await booksApi.purgeBook(accessToken, bookId);
      await fetchBooks();
    },
    [accessToken, fetchBooks],
  );

  const restoreGlossary = useCallback(
    async (item: EntityTrashItem) => {
      if (!accessToken) return;
      await glossaryApi.restoreEntity(item.book_id, item.entity_id, accessToken);
      await fetchGlossary();
    },
    [accessToken, fetchGlossary],
  );

  const purgeGlossary = useCallback(
    async (item: EntityTrashItem) => {
      if (!accessToken) return;
      await glossaryApi.purgeEntity(item.book_id, item.entity_id, accessToken);
      await fetchGlossary();
    },
    [accessToken, fetchGlossary],
  );

  // ── Derived ───────────────────────────────────────────────────────────────

  const allItems = [...bookItems, ...glossaryItems];
  const counts: Record<TrashType, number> = {
    book: bookItems.length,
    glossary: glossaryItems.length,
  };

  return {
    items: allItems,
    counts,
    isLoading,
    refresh,
    restoreBook,
    purgeBook,
    restoreGlossary,
    purgeGlossary,
  };
}
