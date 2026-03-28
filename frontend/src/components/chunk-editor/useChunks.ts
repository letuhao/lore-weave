import { useEffect, useMemo, useRef, useState } from 'react';

export interface ChunkState {
  index: number;
  original: string;
  edited: string | undefined;
  /** Resolved display text: edited if present, otherwise original. */
  text: string;
  isDirty: boolean;
}

/** Split text into paragraph-level chunks (split on one or more blank lines). */
function splitText(text: string): string[] {
  return text.split(/\n{2,}/).filter((c) => c.trim().length > 0);
}

/**
 * Manages chunk-level editing of a text string.
 *
 * - Splits the source text into paragraphs.
 * - Tracks per-chunk edits without touching sibling chunks.
 * - Reassembles into a single string and calls `onChange` whenever edits change.
 * - Detects external text changes (e.g. initial load) and resets edits to avoid
 *   circular update loops.
 */
export function useChunks(text: string, onChange?: (assembled: string) => void) {
  const [edits, setEdits] = useState<Map<number, string>>(new Map());

  // Track the last value we emitted via onChange so we can distinguish our own
  // updates from external ones (e.g. initial API load).
  const lastEmittedRef = useRef(text);
  // Stable ref to onChange — avoids adding it to effect deps.
  const onChangeRef = useRef(onChange);
  useEffect(() => { onChangeRef.current = onChange; });

  // When text changes from outside (not from our own onChange), reset edits.
  useEffect(() => {
    if (text !== lastEmittedRef.current) {
      setEdits(new Map());
      lastEmittedRef.current = text;
    }
  }, [text]);

  const rawChunks = useMemo(() => splitText(text), [text]);

  const chunks: ChunkState[] = useMemo(
    () =>
      rawChunks.map((original, index) => {
        const edited = edits.get(index);
        return {
          index,
          original,
          edited,
          text: edited ?? original,
          isDirty: edited !== undefined,
        };
      }),
    [rawChunks, edits],
  );

  const assembled = useMemo(
    () => chunks.map((c) => c.text).join('\n\n'),
    [chunks],
  );

  const dirtyCount = edits.size;

  // Emit assembled text upward whenever there are pending edits.
  useEffect(() => {
    if (edits.size === 0) return; // nothing to emit when clean
    lastEmittedRef.current = assembled;
    onChangeRef.current?.(assembled);
  }, [assembled, edits.size]);

  function applyEdit(index: number, value: string) {
    setEdits((prev) => {
      const next = new Map(prev);
      // If the edited value equals the original, treat as "no edit"
      if (value === rawChunks[index]) {
        next.delete(index);
      } else {
        next.set(index, value);
      }
      return next;
    });
  }

  function resetEdit(index: number) {
    setEdits((prev) => {
      const next = new Map(prev);
      next.delete(index);
      return next;
    });
  }

  function resetAll() {
    setEdits(new Map());
  }

  return { chunks, assembled, dirtyCount, applyEdit, resetEdit, resetAll };
}
