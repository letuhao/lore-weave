import { useState, useCallback } from 'react';

export type Chunk = { index: number; text: string; dirty: boolean };

export function useChunks(initialText: string) {
  const [chunks, setChunks] = useState<Chunk[]>(() => splitToChunks(initialText));
  const [selected, setSelected] = useState<Set<number>>(new Set());

  const updateChunk = useCallback((index: number, text: string) => {
    setChunks((prev) => prev.map((c) =>
      c.index === index ? { ...c, text, dirty: true } : c,
    ));
  }, []);

  const insertChunk = useCallback((position: number) => {
    setChunks((prev) => {
      const next = [...prev];
      next.splice(position, 0, { index: 0, text: '', dirty: true });
      return next.map((c, i) => ({ ...c, index: i }));
    });
  }, []);

  const deleteChunk = useCallback((index: number) => {
    setChunks((prev) => {
      if (prev.length <= 1) {
        // keep at least one chunk, just clear it
        return [{ index: 0, text: '', dirty: true }];
      }
      return prev.filter((_, i) => i !== index).map((c, i) => ({ ...c, index: i }));
    });
    setSelected((prev) => {
      const next = new Set<number>();
      prev.forEach((i) => { if (i !== index) next.add(i > index ? i - 1 : i); });
      return next;
    });
  }, []);

  const toggleSelect = useCallback((index: number, shift: boolean) => {
    setSelected((prev) => {
      const next = new Set(shift ? prev : []);
      if (prev.has(index) && !shift) next.delete(index);
      else next.add(index);
      return next;
    });
  }, []);

  const clearSelection = useCallback(() => setSelected(new Set()), []);

  const reassemble = useCallback(() => {
    return chunks.map((c) => c.text).join('\n\n');
  }, [chunks]);

  const reset = useCallback((text: string) => {
    setChunks(splitToChunks(text));
    setSelected(new Set());
  }, []);

  const isDirty = chunks.some((c) => c.dirty);

  return {
    chunks, selected, isDirty,
    updateChunk, insertChunk, deleteChunk,
    toggleSelect, clearSelection, reassemble, reset,
  };
}

function splitToChunks(text: string): Chunk[] {
  if (!text.trim()) return [{ index: 0, text: '', dirty: false }];
  return text.split(/\n\n+/).map((t, i) => ({ index: i, text: t.trim(), dirty: false }));
}
