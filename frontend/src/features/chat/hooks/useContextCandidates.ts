import { useEffect, useState } from 'react';
import { useAuth } from '@/auth';
import { booksApi, type Book, type Chapter } from '@/features/books/api';
import { glossaryApi } from '@/features/glossary/api';
import type { GlossaryEntitySummary } from '@/features/glossary/types';

export type ChapterCandidate = Chapter & { bookTitle: string };
export type EntityCandidate = GlossaryEntitySummary & { bookTitle: string };

export interface UseContextCandidatesOptions {
  /** When false, nothing is fetched (lazy mode — the @-mention picker arms this on first trigger). */
  enabled?: boolean;
  /** Fetch glossary entities for one book (ContextPicker mode). Falls back to the first book. */
  glossaryBookId?: string;
  /** Optional kind filter (single-book mode only). */
  glossaryKind?: string;
  /** Fetch glossary entities across every book (mention mode). Overrides glossaryBookId. */
  glossaryAllBooks?: boolean;
}

/**
 * Shared "attachable context" data source for the ContextPicker modal and the
 * inline @-mention picker: the user's books, their chapters, and glossary entities.
 */
export function useContextCandidates(options: UseContextCandidatesOptions = {}) {
  const { enabled = true, glossaryBookId = '', glossaryKind = '', glossaryAllBooks = false } = options;
  const { accessToken } = useAuth();

  const [books, setBooks] = useState<Book[]>([]);
  const [chapters, setChapters] = useState<ChapterCandidate[]>([]);
  const [entities, setEntities] = useState<EntityCandidate[]>([]);

  // Fetch books
  useEffect(() => {
    if (!accessToken || !enabled) return;
    void booksApi
      .listBooks(accessToken)
      .then((r) => setBooks(r.items))
      .catch(() => setBooks([]));
  }, [accessToken, enabled]);

  // Fetch chapters (all books)
  useEffect(() => {
    if (!accessToken || !enabled || books.length === 0) return;
    void Promise.all(
      books.map((b) =>
        booksApi
          .listChapters(accessToken, b.book_id, { limit: 100 })
          .then((r) => r.items.map((ch) => ({ ...ch, bookTitle: b.title })))
          .catch(() => [] as ChapterCandidate[]),
      ),
    ).then((results) => setChapters(results.flat()));
  }, [accessToken, enabled, books]);

  // Fetch glossary entities (single selected book, or all books for mention mode)
  useEffect(() => {
    if (!accessToken || !enabled) return;
    const fetchForBook = (bookId: string, bookTitle: string, kind: string) =>
      glossaryApi
        .listEntities(
          bookId,
          {
            kindCodes: kind ? [kind] : [],
            status: 'all',
            searchQuery: '',
            limit: 100,
            offset: 0,
          },
          accessToken,
        )
        .then((r) => r.items.map((e) => ({ ...e, bookTitle })))
        .catch(() => [] as EntityCandidate[]);

    if (glossaryAllBooks) {
      if (books.length === 0) return;
      void Promise.all(books.map((b) => fetchForBook(b.book_id, b.title, ''))).then((results) =>
        setEntities(results.flat()),
      );
    } else {
      const targetBookId = glossaryBookId || books[0]?.book_id || '';
      if (!targetBookId) return;
      const bookTitle = books.find((b) => b.book_id === targetBookId)?.title ?? '';
      void fetchForBook(targetBookId, bookTitle, glossaryKind).then(setEntities);
    }
  }, [accessToken, enabled, glossaryAllBooks, glossaryBookId, glossaryKind, books]);

  return { books, chapters, entities };
}
