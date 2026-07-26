import { useCallback, useEffect, useState } from 'react';
import {
  leaderboardApi,
  type LeaderboardBook,
  type LeaderboardAuthor,
  type LeaderboardTranslator,
} from '../api';

export type LeaderboardKind = 'books' | 'authors' | 'translators' | 'trending';

const PAGE_SIZE = 20;

/**
 * 14_utility_panels.md D1 — the reusable fetch+filter hook extracted from LeaderboardPage.tsx's
 * 3 inline `useCallback` fetchers + 2 `useEffect`s + 8 `useState`s. Parameterized by `kind` so BOTH
 * the classic tabbed page (re-invoking with a changing `kind` as the user clicks a tab) AND the 4
 * new dock panels (each a fixed `kind` for its whole lifetime, each owning its OWN independent
 * filter state per D2's accepted no-cross-panel-filter-sync simplification) share one
 * implementation (SDK-First) instead of duplicating the fetch/pagination logic.
 *
 * Byte-preserving vs. the original page: same fetch params per kind, the same "trending" sort
 * override (kind === 'trending' forces sort=trending regardless of the local `sort` filter, same
 * as the old `activeTab === 'trending'` check), and the same preview-authors/preview-translators
 * fetch gated on kind === 'books' (feeds `QuickStatsCards`).
 */
export function useLeaderboardList(kind: LeaderboardKind) {
  const [period, setPeriod] = useState('30d');
  const [genre, setGenre] = useState('');
  const [language, setLanguage] = useState('');
  const [sort, setSort] = useState('');

  // Books state — also used by the 'trending' kind (same shape, forced sort param).
  const [books, setBooks] = useState<LeaderboardBook[]>([]);
  const [booksTotal, setBooksTotal] = useState(0);
  const [booksLoading, setBooksLoading] = useState(false);

  // Authors state
  const [authors, setAuthors] = useState<LeaderboardAuthor[]>([]);
  const [authorsTotal, setAuthorsTotal] = useState(0);
  const [authorsLoading, setAuthorsLoading] = useState(false);

  // Translators state
  const [translators, setTranslators] = useState<LeaderboardTranslator[]>([]);
  const [translatorsTotal, setTranslatorsTotal] = useState(0);
  const [translatorsLoading, setTranslatorsLoading] = useState(false);

  // Quick-stats previews (separate from the full lists to avoid overwriting them) — only ever
  // populated for kind === 'books', mirroring LeaderboardPage's original gating.
  const [previewAuthors, setPreviewAuthors] = useState<LeaderboardAuthor[]>([]);
  const [previewTranslators, setPreviewTranslators] = useState<LeaderboardTranslator[]>([]);

  // ── Fetch functions ─────────────────────────────────────────────────────

  const fetchBooks = useCallback(
    async (offset = 0, append = false) => {
      setBooksLoading(true);
      try {
        const sortParam = kind === 'trending' ? 'trending' : sort || undefined;
        const data = await leaderboardApi.listBooks({
          period,
          genre: genre || undefined,
          language: language || undefined,
          sort: sortParam,
          limit: PAGE_SIZE,
          offset,
        });
        setBooks(append ? (prev) => [...prev, ...data.items] : data.items);
        setBooksTotal(data.total);
      } catch {
        // ignore
      } finally {
        setBooksLoading(false);
      }
    },
    [period, genre, language, sort, kind],
  );

  const fetchAuthors = useCallback(
    async (offset = 0, append = false) => {
      setAuthorsLoading(true);
      try {
        const data = await leaderboardApi.listAuthors({ period, limit: PAGE_SIZE, offset });
        setAuthors(append ? (prev) => [...prev, ...data.items] : data.items);
        setAuthorsTotal(data.total);
      } catch {
        // ignore
      } finally {
        setAuthorsLoading(false);
      }
    },
    [period],
  );

  const fetchTranslators = useCallback(
    async (offset = 0, append = false) => {
      setTranslatorsLoading(true);
      try {
        const data = await leaderboardApi.listTranslators({ period, limit: PAGE_SIZE, offset });
        setTranslators(append ? (prev) => [...prev, ...data.items] : data.items);
        setTranslatorsTotal(data.total);
      } catch {
        // ignore
      } finally {
        setTranslatorsLoading(false);
      }
    },
    [period],
  );

  // ── Effects ─────────────────────────────────────────────────────────────

  // Fetch data when kind/filters change
  useEffect(() => {
    if (kind === 'books' || kind === 'trending') {
      fetchBooks(0);
    } else if (kind === 'authors') {
      fetchAuthors(0);
    } else if (kind === 'translators') {
      fetchTranslators(0);
    }
  }, [kind, fetchBooks, fetchAuthors, fetchTranslators]);

  // Fetch quick-stats previews (authors + translators) for the books kind only
  useEffect(() => {
    if (kind === 'books') {
      leaderboardApi.listAuthors({ period, limit: 3 }).then((d) => setPreviewAuthors(d.items)).catch(() => {});
      leaderboardApi.listTranslators({ period, limit: 3 }).then((d) => setPreviewTranslators(d.items)).catch(() => {});
    }
  }, [kind, period]);

  const showPodium = (kind === 'books' || kind === 'trending') && books.length >= 3;
  const isLoading =
    kind === 'books' || kind === 'trending'
      ? booksLoading
      : kind === 'authors'
        ? authorsLoading
        : translatorsLoading;

  return {
    period,
    setPeriod,
    genre,
    setGenre,
    language,
    setLanguage,
    sort,
    setSort,
    books,
    booksTotal,
    booksLoading,
    fetchBooks,
    authors,
    authorsTotal,
    authorsLoading,
    fetchAuthors,
    translators,
    translatorsTotal,
    translatorsLoading,
    fetchTranslators,
    previewAuthors,
    previewTranslators,
    showPodium,
    isLoading,
  };
}

export type UseLeaderboardListResult = ReturnType<typeof useLeaderboardList>;
