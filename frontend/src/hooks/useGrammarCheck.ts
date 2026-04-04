import React, { useState, useCallback, useRef, useEffect } from 'react';
import {
  checkGrammar,
  splitParagraphsWithPositions,
  getParagraphsAroundCursor,
  type GrammarMatch,
  type ParagraphInfo,
} from '@/features/grammar/api';

const STORAGE_KEY = 'lw_grammar_check';

/** Persistent toggle for grammar checking (default: enabled). */
export function useGrammarEnabled() {
  const [enabled, setEnabledState] = useState(() => {
    const v = localStorage.getItem(STORAGE_KEY);
    return v !== null ? v === 'true' : true;
  });
  const setEnabled = useCallback((v: boolean) => {
    setEnabledState(v);
    localStorage.setItem(STORAGE_KEY, String(v));
  }, []);
  return [enabled, setEnabled] as const;
}

/**
 * Manages grammar check results for a set of chunks.
 *
 * - `checkChunk(index, text)` — called on chunk blur; clears stale result, runs async check.
 * - `checkAll(chunks)` — batch-check all chunks (used on initial load).
 * - `clear()` — clear all results (used on structural changes like insert/delete).
 * - `results` — Map<chunkIndex, GrammarMatch[]>.
 * - `totalIssues` — sum of all matches across all chunks.
 */
export function useGrammarCheck(enabled: boolean, language = 'auto') {
  const [results, setResults] = useState<Map<number, GrammarMatch[]>>(
    new Map(),
  );
  const cacheRef = useRef<Map<string, GrammarMatch[]>>(new Map());

  const checkChunk = useCallback(
    async (index: number, text: string) => {
      // Clear old result immediately so stale decorations don't render
      setResults((prev) => {
        const n = new Map(prev);
        n.delete(index);
        return n;
      });

      if (!enabled || !text.trim()) return;

      const cached = cacheRef.current.get(text);
      if (cached) {
        setResults((prev) => {
          const n = new Map(prev);
          n.set(index, cached);
          return n;
        });
        return;
      }

      const matches = await checkGrammar(text, language);
      cacheRef.current.set(text, matches);
      setResults((prev) => {
        const n = new Map(prev);
        n.set(index, matches);
        return n;
      });
    },
    [enabled, language],
  );

  const checkAll = useCallback(
    async (chunks: Array<{ index: number; text: string }>) => {
      if (!enabled) return;
      await Promise.all(chunks.map((c) => checkChunk(c.index, c.text)));
    },
    [enabled, checkChunk],
  );

  const clear = useCallback(() => setResults(new Map()), []);

  // Clear when disabled
  useEffect(() => {
    if (!enabled) clear();
  }, [enabled, clear]);

  let totalIssues = 0;
  results.forEach((m) => {
    totalIssues += m.length;
  });

  return { results, checkChunk, checkAll, clear, totalIssues };
}

// ── Source mode grammar check ───────────────────────────────────────────────



export interface SourceGrammarResult {
  /** paragraph index → matches (offsets relative to paragraph start) */
  paragraphs: Map<number, { info: ParagraphInfo; matches: GrammarMatch[] }>;
  totalIssues: number;
}

const MAX_PARAGRAPH_LENGTH = 10_000; // skip huge paragraphs

/**
 * Debounced grammar check for source mode.
 *
 * Only checks the paragraph at cursor + 1 neighbor above/below (max 3).
 * Caches results by text content so unchanged paragraphs are instant.
 *
 * @param textareaRef - ref to the source textarea (reads cursor position at check time)
 */
export function useSourceGrammarCheck(
  sourceBody: string,
  textareaRef: React.RefObject<HTMLTextAreaElement | null>,
  enabled: boolean,
  language = 'auto',
  debounceMs = 1500,
): SourceGrammarResult & { clear: () => void } {
  const [paragraphs, setParagraphs] = useState<
    Map<number, { info: ParagraphInfo; matches: GrammarMatch[] }>
  >(new Map());
  const cacheRef = useRef<Map<string, GrammarMatch[]>>(new Map());
  const timerRef = useRef<ReturnType<typeof setTimeout>>();
  // Track the current sourceBody in a ref so the timeout closure reads the latest
  const bodyRef = useRef(sourceBody);
  bodyRef.current = sourceBody;

  useEffect(() => {
    if (!enabled || !sourceBody.trim()) {
      setParagraphs(new Map());
      return;
    }

    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(async () => {
      const currentBody = bodyRef.current;
      const allParas = splitParagraphsWithPositions(currentBody);
      const cursor = textareaRef.current?.selectionStart ?? 0;
      const indicesToCheck = getParagraphsAroundCursor(allParas, cursor);

      for (const idx of indicesToCheck) {
        const para = allParas[idx];
        if (!para || !para.text.trim() || para.text.length > MAX_PARAGRAPH_LENGTH) continue;

        // Use cache if available
        const cached = cacheRef.current.get(para.text);
        if (cached !== undefined) {
          setParagraphs((prev) => {
            const n = new Map(prev);
            n.set(idx, { info: para, matches: cached });
            return n;
          });
          continue;
        }

        const matches = await checkGrammar(para.text, language);
        cacheRef.current.set(para.text, matches);
        setParagraphs((prev) => {
          const n = new Map(prev);
          n.set(idx, { info: para, matches });
          return n;
        });
      }

      // Prune results for paragraphs that no longer exist
      setParagraphs((prev) => {
        const maxIdx = allParas.length;
        let changed = false;
        const n = new Map(prev);
        for (const key of n.keys()) {
          if (key >= maxIdx) { n.delete(key); changed = true; }
        }
        return changed ? n : prev;
      });
    }, debounceMs);

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sourceBody, enabled, language, debounceMs]);

  const clear = useCallback(() => setParagraphs(new Map()), []);

  let totalIssues = 0;
  paragraphs.forEach(({ matches }) => {
    totalIssues += matches.length;
  });

  return { paragraphs, totalIssues, clear };
}
