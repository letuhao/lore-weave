import { useCallback, useEffect, useState } from 'react';
import type { JSONContent } from '@tiptap/react';
import { useAuth } from '@/auth';
import { booksApi, type Book, type Chapter, type ReadingProgress } from '@/features/books/api';
import { versionsApi } from '@/features/translation/api';
import type { LanguageOption } from '@/components/reader/TOCSidebar';
import { extractText } from '@/lib/tiptap-utils';

/** CJK Unicode ranges: CJK Unified Ideographs, Hiragana, Katakana, Hangul */
const CJK_REGEX = /[　-鿿가-힯＀-￯]/;

/** Shared with ReaderPage AND BookReaderPanel — extracted verbatim so the reading-time
 *  estimate isn't computed two different ways in two places. */
export function computeReadingStats(blocks: JSONContent[], language?: string) {
  const text = blocks.map((b) => extractText(b)).join(' ');
  const isCJK = CJK_REGEX.test(text) || ['ja', 'zh', 'ko'].includes(language ?? '');

  if (isCJK) {
    // CJK: count characters (excluding spaces/punctuation), ~400 chars/min
    const chars = text.replace(/[\s\p{P}]/gu, '').length;
    const minutes = Math.max(1, Math.round(chars / 400));
    return { count: chars.toLocaleString(), unit: 'chars', minutes };
  }

  // Latin: count words, ~230 wpm
  const words = text.trim() ? text.trim().split(/\s+/).length : 0;
  const minutes = Math.max(1, Math.round(words / 230));
  return { count: words.toLocaleString(), unit: 'words', minutes };
}

/**
 * Content-bootstrapping hook (14_utility_panels.md Phase C3, docs/standards/dockable-gui.md
 * DOCK-2/DOCK-10) — fetches book/chapters/chapter-blocks/language-versions for a
 * `(bookId, chapterId)` pair. Router-free: bookId/chapterId arrive as ARGS, never via
 * `useParams()`, so both the `/books/:bookId/chapters/:chapterId/read` route (ReaderPage) and
 * the params-driven `book-reader` dock panel (BookReaderPanel, DOCK-7 F1) share ONE fetch/state
 * implementation instead of forking it.
 *
 * UI-only toggle state (tocOpen/themeOpen/ttsSettingsOpen/showIndices/autoNext/autoScrollTTS) is
 * deliberately NOT here — it stays page/panel-local (Tier-1), same precedent `useBooksList` set
 * for its search/langFilter/create-dialog fields. This hook owns only the fetch-derived state:
 * book, chapters, chapter, blocks/originalBlocks, languages, activeLanguage, langVersionMap,
 * langLoading, readProgress, loading — plus the language-switch action and the chapter-position
 * derivations (currentIdx/prevCh/nextCh/progress) every consumer needs.
 *
 * Byte-preserving extraction: the fetch effect and handleLanguageChange below are copied
 * verbatim from ReaderPage's original inline implementation (including that a request race
 * isn't guarded with a `cancelled` flag — matching the original's exact behavior, not "fixed"
 * as part of this reuse extraction).
 */
export function useBookReaderContent(bookId: string, chapterId: string) {
  const { accessToken } = useAuth();
  const [originalBlocks, setOriginalBlocks] = useState<JSONContent[]>([]);
  const [blocks, setBlocks] = useState<JSONContent[]>([]);
  const [chapter, setChapter] = useState<Chapter | null>(null);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [book, setBook] = useState<Book | null>(null);
  const [loading, setLoading] = useState(true);

  // Language state
  const [languages, setLanguages] = useState<LanguageOption[]>([]);
  const [activeLanguage, setActiveLanguage] = useState('');
  // Map: language code → active translation version ID
  const [langVersionMap, setLangVersionMap] = useState<Record<string, string>>({});
  const [langLoading, setLangLoading] = useState(false);
  const [readProgress, setReadProgress] = useState<ReadingProgress[]>([]);

  useEffect(() => {
    if (!accessToken || !bookId || !chapterId) return;
    setLoading(true);
    Promise.all([
      booksApi.getBook(accessToken, bookId),
      booksApi.getDraft(accessToken, bookId, chapterId),
      booksApi.listChapters(accessToken, bookId, { lifecycle_state: 'active', limit: 100 }),
      versionsApi.listChapterVersions(accessToken, chapterId).catch(() => null),
      booksApi.getReadingProgress(accessToken, bookId).catch(() => ({ items: [] })),
    ]).then(([b, d, chs, versions, rp]) => {
      setReadProgress(rp.items);
      setBook(b);
      const body = d.body as JSONContent | null;
      const origBlocks = body?.content ?? [];
      setOriginalBlocks(origBlocks);
      setBlocks(origBlocks);
      setChapter(chs.items.find((c) => c.chapter_id === chapterId) ?? null);
      setChapters(chs.items);

      // Build language options
      const origLang = b.original_language ?? 'original';
      const langs: LanguageOption[] = [{ code: origLang, isOriginal: true }];
      const versionMap: Record<string, string> = {};
      if (versions?.languages) {
        for (const g of versions.languages) {
          if (g.target_language !== origLang) {
            langs.push({ code: g.target_language, isOriginal: false });
          }
          if (g.active_id) {
            versionMap[g.target_language] = g.active_id;
          }
        }
      }
      setLanguages(langs);
      setLangVersionMap(versionMap);
      setActiveLanguage(origLang);
    }).catch(() => {}).finally(() => setLoading(false));
  }, [accessToken, bookId, chapterId]);

  /** Convert flat translated text to paragraph blocks for ContentRenderer */
  const textToBlocks = useCallback((text: string): JSONContent[] => {
    return text.split(/\n\n+/).filter(Boolean).map((p) => ({
      type: 'paragraph',
      content: [{ type: 'text', text: p }],
    }));
  }, []);

  /** Switch reading language */
  const handleLanguageChange = useCallback(async (lang: string) => {
    setActiveLanguage(lang);
    const origLang = book?.original_language ?? 'original';
    if (lang === origLang) {
      setBlocks(originalBlocks);
      return;
    }
    const versionId = langVersionMap[lang];
    if (!versionId || !accessToken) return;
    setLangLoading(true);
    try {
      const version = await versionsApi.getChapterVersion(accessToken, chapterId, versionId);
      if (version.translated_body_format === 'json' && Array.isArray(version.translated_body_json)) {
        // Phase 8F: block-level JSONB translation — render natively
        setBlocks(version.translated_body_json as JSONContent[]);
      } else if (version.translated_body) {
        // Legacy: plain text → synthetic paragraph blocks
        setBlocks(textToBlocks(version.translated_body));
      }
    } catch {
      setBlocks(originalBlocks);
      setActiveLanguage(origLang);
    } finally {
      setLangLoading(false);
    }
  }, [book, originalBlocks, langVersionMap, accessToken, chapterId, textToBlocks]);

  const currentIdx = chapters.findIndex((c) => c.chapter_id === chapterId);
  const prevCh = currentIdx > 0 ? chapters[currentIdx - 1] : null;
  const nextCh = currentIdx < chapters.length - 1 ? chapters[currentIdx + 1] : null;
  const progress = chapters.length > 0 ? ((currentIdx + 1) / chapters.length) * 100 : 0;

  return {
    book,
    chapters,
    chapter,
    blocks,
    originalBlocks,
    languages,
    activeLanguage,
    langVersionMap,
    langLoading,
    readProgress,
    loading,
    handleLanguageChange,
    currentIdx,
    prevCh,
    nextCh,
    progress,
  };
}

export type UseBookReaderContentResult = ReturnType<typeof useBookReaderContent>;
