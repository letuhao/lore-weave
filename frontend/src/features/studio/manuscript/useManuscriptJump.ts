import { useEffect, useMemo, useRef, useState } from 'react';
import { booksApi, type Chapter } from '@/features/books/api';
import { compositionApi } from '@/features/composition/api';
import type { OutlineSearchHit } from '@/features/composition/types';
import { useWorkResolution } from '@/features/composition/hooks/useWork';
import { useActiveWorkId } from '@/features/composition/hooks/useActiveWork';
import { resolveActiveWork } from '@/features/composition/workSelect';
import type { JumpResult } from './types';

const LIMIT = 30;
const DEBOUNCE_MS = 180;

function outlineHitToResult(h: OutlineSearchHit): JumpResult {
  const kind = h.kind === 'arc' ? 'arc' : h.kind === 'scene' ? 'scene' : 'chapter';
  return {
    id: h.id,
    kind,
    title: h.title || '(untitled)',
    number: h.story_order,
    status: h.status,
    chapterId: h.chapter_id,
    path: h.path ?? [],
  };
}

function chapterToResult(c: Chapter): JumpResult {
  return {
    id: c.chapter_id,
    kind: 'chapter',
    title: c.title || c.original_filename || `#${c.sort_order}`,
    number: c.sort_order,
    status: null,
    chapterId: c.chapter_id,
    path: [],
  };
}

/**
 * The shared manuscript jump/search layer (nav jump box + #06a Quick Open — do NOT write a
 * second query path). Resolves the book's source (Work → outline search; none → book-service
 * chapter search) and queries the SERVER, so it reaches every node across a 10k-chapter book —
 * not just the lazy-loaded tree window (which was the v1 client-filter's blind spot). Debounced
 * with a generation guard so a stale response never overwrites a newer query's results.
 */
export function useManuscriptJump(bookId: string, token: string | null) {
  const work = useWorkResolution(bookId, token);
  const { data: activeWorkId } = useActiveWorkId(bookId, token);
  // EC-3d: the ACTIVE Work's project (per-book pref, else canonical) — NOT candidates[0].
  const projectId = useMemo(
    () => resolveActiveWork(work.data, activeWorkId)?.project_id ?? null,
    [work.data, activeWorkId],
  );

  const source: 'pending' | 'chapters' | 'outline' =
    work.isLoading ? 'pending' : projectId ? 'outline' : 'chapters';

  const [query, setQuery] = useState('');
  const [results, setResults] = useState<JumpResult[]>([]);
  const [searching, setSearching] = useState(false);
  const genRef = useRef(0);

  useEffect(() => {
    const q = query.trim();
    const gen = ++genRef.current; // any in-flight/queued search from a prior query is now stale
    if (!q || source === 'pending' || !token) {
      setResults([]);
      setSearching(false);
      return;
    }
    setSearching(true);
    const timer = setTimeout(async () => {
      try {
        let items: JumpResult[] = [];
        if (source === 'outline' && projectId) {
          const r = await compositionApi.searchOutline(projectId, token, { q, limit: LIMIT });
          items = r.items.map(outlineHitToResult);
        } else if (source === 'chapters') {
          const r = await booksApi.listChaptersPage(token, bookId, { q, limit: LIMIT });
          items = r.items.map(chapterToResult);
        }
        if (genRef.current === gen) setResults(items);
      } catch {
        if (genRef.current === gen) setResults([]);
      } finally {
        if (genRef.current === gen) setSearching(false);
      }
    }, DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [query, source, projectId, bookId, token]);

  return { query, setQuery, results, searching, active: query.trim().length > 0 };
}
