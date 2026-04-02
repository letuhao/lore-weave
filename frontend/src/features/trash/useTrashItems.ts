import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@/auth';
import { booksApi, type Chapter } from '@/features/books/api';
import { glossaryApi } from '@/features/glossary/api';
import { chatApi } from '@/features/chat-v2/api';
import type { EntityTrashItem } from '@/features/glossary/types';
import type { ChatSession } from '@/features/chat-v2/types';
import {
  bookToTrashItem,
  chapterToTrashItem,
  glossaryToTrashItem,
  chatSessionToTrashItem,
  type TrashItem,
  type TrashType,
} from './types';

interface UseTrashItemsReturn {
  items: TrashItem[];
  counts: Record<TrashType, number>;
  isLoading: boolean;
  refresh: () => Promise<void>;
  restoreItem: (item: TrashItem) => Promise<void>;
  purgeItem: (item: TrashItem) => Promise<void>;
}

export function useTrashItems(): UseTrashItemsReturn {
  const { accessToken } = useAuth();
  const [bookItems, setBookItems] = useState<TrashItem[]>([]);
  const [chapterItems, setChapterItems] = useState<TrashItem[]>([]);
  const [glossaryItems, setGlossaryItems] = useState<TrashItem[]>([]);
  const [chatItems, setChatItems] = useState<TrashItem[]>([]);
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

  // ── Fetch chapters (across all books) ─────────────────────────────────────

  const fetchChapters = useCallback(async () => {
    if (!accessToken) return;
    try {
      const booksRes = await booksApi.listBooks(accessToken);
      const bookMap = new Map(booksRes.items.map((b) => [b.book_id, b.title]));

      const results = await Promise.all(
        booksRes.items.map((b) =>
          booksApi
            .listChapters(accessToken, b.book_id, { lifecycle_state: 'trashed', limit: 100 })
            .then((r) => r.items.map((ch) => chapterToTrashItem(ch, bookMap.get(b.book_id))))
            .catch(() => [] as TrashItem[]),
        ),
      );

      setChapterItems(
        results.flat().sort((a, b) => new Date(b.deletedAt).getTime() - new Date(a.deletedAt).getTime()),
      );
    } catch {
      setChapterItems([]);
    }
  }, [accessToken]);

  // ── Fetch glossary (across all books) ─────────────────────────────────────

  const fetchGlossary = useCallback(async () => {
    if (!accessToken) return;
    try {
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

  // ── Fetch chat sessions (archived) ────────────────────────────────────────

  const fetchChat = useCallback(async () => {
    if (!accessToken) return;
    try {
      const res = await chatApi.listSessions(accessToken, 'archived');
      setChatItems(res.items.map(chatSessionToTrashItem));
    } catch {
      setChatItems([]);
    }
  }, [accessToken]);

  // ── Combined refresh ──────────────────────────────────────────────────────

  const refresh = useCallback(async () => {
    setIsLoading(true);
    await Promise.all([fetchBooks(), fetchChapters(), fetchGlossary(), fetchChat()]);
    setIsLoading(false);
  }, [fetchBooks, fetchChapters, fetchGlossary, fetchChat]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // ── Unified restore/purge ─────────────────────────────────────────────────

  const restoreItem = useCallback(
    async (item: TrashItem) => {
      if (!accessToken) return;
      switch (item.type) {
        case 'book':
          await booksApi.restoreBook(accessToken, item.id);
          await fetchBooks();
          break;
        case 'chapter': {
          const ch = item.raw as Chapter;
          await booksApi.restoreChapter(accessToken, ch.book_id, ch.chapter_id);
          await fetchChapters();
          break;
        }
        case 'glossary': {
          const ent = item.raw as EntityTrashItem;
          await glossaryApi.restoreEntity(ent.book_id, ent.entity_id, accessToken);
          await fetchGlossary();
          break;
        }
        case 'chat': {
          const sess = item.raw as ChatSession;
          await chatApi.patchSession(accessToken, sess.session_id, { status: 'active' });
          await fetchChat();
          break;
        }
      }
    },
    [accessToken, fetchBooks, fetchChapters, fetchGlossary, fetchChat],
  );

  const purgeItem = useCallback(
    async (item: TrashItem) => {
      if (!accessToken) return;
      switch (item.type) {
        case 'book':
          await booksApi.purgeBook(accessToken, item.id);
          await fetchBooks();
          break;
        case 'chapter': {
          const ch = item.raw as Chapter;
          await booksApi.purgeChapter(accessToken, ch.book_id, ch.chapter_id);
          await fetchChapters();
          break;
        }
        case 'glossary': {
          const ent = item.raw as EntityTrashItem;
          await glossaryApi.purgeEntity(ent.book_id, ent.entity_id, accessToken);
          await fetchGlossary();
          break;
        }
        case 'chat': {
          const sess = item.raw as ChatSession;
          await chatApi.deleteSession(accessToken, sess.session_id);
          await fetchChat();
          break;
        }
      }
    },
    [accessToken, fetchBooks, fetchChapters, fetchGlossary, fetchChat],
  );

  // ── Derived ───────────────────────────────────────────────────────────────

  const allItems = [...bookItems, ...chapterItems, ...glossaryItems, ...chatItems];
  const counts: Record<TrashType, number> = {
    book: bookItems.length,
    chapter: chapterItems.length,
    glossary: glossaryItems.length,
    chat: chatItems.length,
  };

  return {
    items: allItems,
    counts,
    isLoading,
    refresh,
    restoreItem,
    purgeItem,
  };
}
