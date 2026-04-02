import { useCallback, useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { booksApi, type Chapter } from '@/features/books/api';
import { glossaryApi } from '@/features/glossary/api';
import {
  bookToTrashItem,
  chapterToTrashItem,
  glossaryToTrashItem,
  chatSessionToTrashItem,
  type TrashItem,
  type TrashType,
  type EntityTrashItem,
  type ChatSession,
} from './types';

const API_BASE = () => import.meta.env.VITE_API_BASE || 'http://localhost:3000';

// Inline minimal chat API (full chat is MIG-02)
async function listArchivedSessions(token: string): Promise<{ items: ChatSession[] }> {
  const res = await fetch(`${API_BASE()}/v1/chat/sessions?status=archived`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) return { items: [] };
  return res.json();
}

async function restoreChatSession(token: string, sessionId: string): Promise<void> {
  await fetch(`${API_BASE()}/v1/chat/sessions/${sessionId}`, {
    method: 'PATCH',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ status: 'active' }),
  });
}

async function deleteChatSession(token: string, sessionId: string): Promise<void> {
  await fetch(`${API_BASE()}/v1/chat/sessions/${sessionId}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  });
}

// Inline glossary trash API (missing from v2 glossaryApi)
async function listGlossaryTrash(token: string, bookId: string): Promise<{ items: EntityTrashItem[] }> {
  const res = await fetch(`${API_BASE()}/v1/books/${bookId}/glossary/entities?lifecycle_state=trashed&limit=100`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) return { items: [] };
  return res.json();
}

async function restoreGlossaryEntity(token: string, bookId: string, entityId: string): Promise<void> {
  await fetch(`${API_BASE()}/v1/books/${bookId}/glossary/entities/${entityId}/restore`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  });
}

async function purgeGlossaryEntity(token: string, bookId: string, entityId: string): Promise<void> {
  await fetch(`${API_BASE()}/v1/books/${bookId}/glossary/entities/${entityId}/purge`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function useTrashItems() {
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();
  const [bookItems, setBookItems] = useState<TrashItem[]>([]);
  const [chapterItems, setChapterItems] = useState<TrashItem[]>([]);
  const [glossaryItems, setGlossaryItems] = useState<TrashItem[]>([]);
  const [chatItems, setChatItems] = useState<TrashItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const fetchBooks = useCallback(async () => {
    if (!accessToken) return;
    try {
      const res = await booksApi.listTrash(accessToken);
      setBookItems(res.items.map(bookToTrashItem));
    } catch { setBookItems([]); }
  }, [accessToken]);

  const fetchChapters = useCallback(async () => {
    if (!accessToken) return;
    try {
      const booksRes = await booksApi.listBooks(accessToken);
      const bookMap = new Map(booksRes.items.map((b) => [b.book_id, b.title]));
      const results = await Promise.all(
        booksRes.items.map((b) =>
          booksApi.listChapters(accessToken, b.book_id, { lifecycle_state: 'trashed', limit: 100 })
            .then((r) => r.items.map((ch) => chapterToTrashItem(ch, bookMap.get(b.book_id))))
            .catch(() => [] as TrashItem[]),
        ),
      );
      setChapterItems(results.flat().sort((a, b) => new Date(b.deletedAt).getTime() - new Date(a.deletedAt).getTime()));
    } catch { setChapterItems([]); }
  }, [accessToken]);

  const fetchGlossary = useCallback(async () => {
    if (!accessToken) return;
    try {
      const booksRes = await booksApi.listBooks(accessToken);
      const bookMap = new Map(booksRes.items.map((b) => [b.book_id, b.title]));
      const results = await Promise.all(
        booksRes.items.map((b) =>
          listGlossaryTrash(accessToken, b.book_id)
            .then((r) => r.items.map((it) => glossaryToTrashItem(it, bookMap.get(b.book_id))))
            .catch(() => [] as TrashItem[]),
        ),
      );
      setGlossaryItems(results.flat().sort((a, b) => new Date(b.deletedAt).getTime() - new Date(a.deletedAt).getTime()));
    } catch { setGlossaryItems([]); }
  }, [accessToken]);

  const fetchChat = useCallback(async () => {
    if (!accessToken) return;
    try {
      const res = await listArchivedSessions(accessToken);
      setChatItems(res.items.map(chatSessionToTrashItem));
    } catch { setChatItems([]); }
  }, [accessToken]);

  const refresh = useCallback(async () => {
    setIsLoading(true);
    await Promise.all([fetchBooks(), fetchChapters(), fetchGlossary(), fetchChat()]);
    setIsLoading(false);
  }, [fetchBooks, fetchChapters, fetchGlossary, fetchChat]);

  useEffect(() => { void refresh(); }, [refresh]);

  const restoreItem = useCallback(async (item: TrashItem) => {
    if (!accessToken) return;
    switch (item.type) {
      case 'book':
        await booksApi.restoreBook(accessToken, item.id);
        await fetchBooks();
        queryClient.removeQueries({ queryKey: ['books'] });
        break;
      case 'chapter': {
        const ch = item.raw as Chapter;
        await booksApi.restoreChapter(accessToken, ch.book_id, ch.chapter_id);
        await fetchChapters();
        // Remove stale cache AND refetch — invalidate alone isn't enough with localStorage persistence
        queryClient.removeQueries({ queryKey: ['chapters', ch.book_id] });
        queryClient.invalidateQueries({ queryKey: ['book', ch.book_id] });
        break;
      }
      case 'glossary': {
        const ent = item.raw as EntityTrashItem;
        await restoreGlossaryEntity(accessToken, ent.book_id, ent.entity_id);
        await fetchGlossary();
        queryClient.removeQueries({ queryKey: ['glossary-entities', ent.book_id] });
        break;
      }
      case 'chat': {
        const sess = item.raw as ChatSession;
        await restoreChatSession(accessToken, sess.session_id);
        await fetchChat();
        break;
      }
    }
  }, [accessToken, fetchBooks, fetchChapters, fetchGlossary, fetchChat, queryClient]);

  const purgeItem = useCallback(async (item: TrashItem) => {
    if (!accessToken) return;
    switch (item.type) {
      case 'book':
        await booksApi.purgeBook(accessToken, item.id);
        await fetchBooks();
        queryClient.invalidateQueries({ queryKey: ['books'] });
        break;
      case 'chapter': {
        const ch = item.raw as Chapter;
        await booksApi.purgeChapter(accessToken, ch.book_id, ch.chapter_id);
        await fetchChapters();
        queryClient.invalidateQueries({ queryKey: ['chapters', ch.book_id] });
        break;
      }
      case 'glossary': {
        const ent = item.raw as EntityTrashItem;
        await purgeGlossaryEntity(accessToken, ent.book_id, ent.entity_id);
        await fetchGlossary();
        queryClient.invalidateQueries({ queryKey: ['glossary-entities', ent.book_id] });
        break;
      }
      case 'chat': {
        const sess = item.raw as ChatSession;
        await deleteChatSession(accessToken, sess.session_id);
        await fetchChat();
        break;
      }
    }
  }, [accessToken, fetchBooks, fetchChapters, fetchGlossary, fetchChat, queryClient]);

  return {
    items: [...bookItems, ...chapterItems, ...glossaryItems, ...chatItems],
    counts: { book: bookItems.length, chapter: chapterItems.length, glossary: glossaryItems.length, chat: chatItems.length } as Record<TrashType, number>,
    isLoading,
    refresh,
    restoreItem,
    purgeItem,
  };
}
