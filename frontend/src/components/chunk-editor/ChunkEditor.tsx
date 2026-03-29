import { useCallback, useState } from 'react';
import { toast } from 'sonner';
import { Bot, Check, Languages, Loader2, RotateCcw, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useChunks } from './useChunks';
import { ChunkItem } from './ChunkItem';

interface ChunkEditorProps {
  text: string;
  onChange: (value: string) => void;
  /** Translate a chunk's text. Returns the translated text. */
  onTranslateChunk?: (text: string) => Promise<string>;
}

/**
 * Chunk-based view of a text document.
 *
 * Selection model:
 *  - Click       → select that chunk only (set as range anchor)
 *  - Shift+click → extend/shrink selection from anchor to clicked chunk
 *  - Click same  → deselect when it was the only selection
 *
 * When ≥1 chunk is selected, a selection bar appears with:
 *  - "N chunks selected (range: X–Y)"
 *  - Copy with context (prev + all selected + following)
 *  - Deselect all
 */
export function ChunkEditor({ text, onChange, onTranslateChunk }: ChunkEditorProps) {
  const { chunks, dirtyCount, applyEdit, resetEdit, resetAll } = useChunks(text, onChange);

  const [selectedIndices, setSelectedIndices] = useState<Set<number>>(new Set());
  const [anchorIndex, setAnchorIndex] = useState<number | null>(null);
  const [copyDone, setCopyDone] = useState(false);
  const [translatingIndices, setTranslatingIndices] = useState<Set<number>>(new Set());

  function handleSelect(index: number, shiftKey: boolean) {
    if (shiftKey && anchorIndex !== null) {
      // Range select from anchor → index (replaces current selection)
      const lo = Math.min(anchorIndex, index);
      const hi = Math.max(anchorIndex, index);
      const range = new Set<number>();
      for (let i = lo; i <= hi; i++) range.add(i);
      setSelectedIndices(range);
    } else {
      // Single click — toggle if already sole selection, otherwise narrow to this one
      setSelectedIndices((prev) => {
        if (prev.size === 1 && prev.has(index)) return new Set(); // deselect
        return new Set([index]);
      });
      setAnchorIndex(index);
    }
  }

  function clearSelection() {
    setSelectedIndices(new Set());
    setAnchorIndex(null);
  }

  /**
   * Copy all selected chunks with surrounding context for AI agents.
   * Format:
   *   [Chunks 3–5 of 47]
   *   [Previous]  chunk before selection
   *   [Chunk 3]   selected chunk text
   *   [Chunk 4]   ...
   *   [Chunk 5]   ...
   *   [Following] chunk after selection
   */
  function copySelection() {
    const sorted = [...selectedIndices].sort((a, b) => a - b);
    if (sorted.length === 0) return;

    const first = sorted[0];
    const last = sorted[sorted.length - 1];
    const total = chunks.length;

    const isSingle = sorted.length === 1;
    const header = isSingle
      ? `[Chunk ${first + 1} of ${total}]`
      : `[Chunks ${first + 1}–${last + 1} of ${total}]`;

    const parts: string[] = [header];
    if (first > 0) parts.push(`\n[Previous]\n${chunks[first - 1].text}`);

    if (isSingle) {
      parts.push(`\n[Current]\n${chunks[first].text}`);
    } else {
      for (const i of sorted) {
        parts.push(`\n[Chunk ${i + 1}]\n${chunks[i].text}`);
      }
    }

    if (last < total - 1) parts.push(`\n[Following]\n${chunks[last + 1].text}`);

    void navigator.clipboard.writeText(parts.join('\n')).then(() => {
      setCopyDone(true);
      setTimeout(() => setCopyDone(false), 1500);
    });
  }

  const translateChunk = useCallback(
    async (index: number) => {
      if (!onTranslateChunk) return;
      // Guard against double-fire via setState (avoids stale closure on translatingIndices)
      let alreadyTranslating = false;
      setTranslatingIndices((prev) => {
        if (prev.has(index)) { alreadyTranslating = true; return prev; }
        return new Set(prev).add(index);
      });
      if (alreadyTranslating) return;
      try {
        const translated = await onTranslateChunk(chunks[index].text);
        applyEdit(index, translated);
      } finally {
        setTranslatingIndices((prev) => {
          const next = new Set(prev);
          next.delete(index);
          return next;
        });
      }
    },
    [onTranslateChunk, chunks, applyEdit],
  );

  const translateSelected = useCallback(async () => {
    if (!onTranslateChunk || selectedIndices.size === 0) return;
    const indices = [...selectedIndices].sort((a, b) => a - b);
    // Mark all as translating
    setTranslatingIndices((prev) => {
      const next = new Set(prev);
      for (const i of indices) next.add(i);
      return next;
    });
    // Translate in parallel
    const results = await Promise.allSettled(
      indices.map((i) => onTranslateChunk(chunks[i].text)),
    );
    let failCount = 0;
    for (let j = 0; j < indices.length; j++) {
      const result = results[j];
      if (result.status === 'fulfilled') {
        applyEdit(indices[j], result.value);
      } else {
        failCount++;
      }
    }
    if (failCount > 0) {
      const ok = indices.length - failCount;
      toast.error(`${failCount} of ${indices.length} chunks failed to translate${ok > 0 ? ` (${ok} succeeded)` : ''}`);
    }
    setTranslatingIndices((prev) => {
      const next = new Set(prev);
      for (const i of indices) next.delete(i);
      return next;
    });
  }, [onTranslateChunk, selectedIndices, chunks, applyEdit]);

  const isTranslatingAny = translatingIndices.size > 0;

  const selectionCount = selectedIndices.size;
  const sortedSel = selectionCount > 0 ? [...selectedIndices].sort((a, b) => a - b) : null;

  if (chunks.length === 0) {
    return (
      <div className="flex h-full items-center justify-center p-8 text-sm text-muted-foreground">
        No paragraphs to display. Write something in editor mode first.
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* ── Dirty bar ─────────────────────────────────────────────────────── */}
      {dirtyCount > 0 && (
        <div className="flex shrink-0 items-center gap-3 border-b bg-amber-50/60 px-4 py-1.5 text-xs dark:bg-amber-900/10">
          <span className="text-amber-600 dark:text-amber-400">
            {dirtyCount} chunk{dirtyCount !== 1 ? 's' : ''} edited
          </span>
          <Button
            size="sm"
            variant="ghost"
            className="h-6 gap-1 px-2 text-xs text-muted-foreground hover:text-foreground"
            onClick={resetAll}
          >
            <RotateCcw className="h-3 w-3" />
            Reset all
          </Button>
          <span className="ml-auto text-muted-foreground/60">Save draft to persist changes</span>
        </div>
      )}

      {/* ── Selection bar ─────────────────────────────────────────────────── */}
      {selectionCount > 0 && sortedSel && (
        <div className="flex shrink-0 items-center gap-3 border-b bg-primary/5 px-4 py-1.5 text-xs dark:bg-primary/10">
          <span className="font-medium text-primary">
            {selectionCount} chunk{selectionCount !== 1 ? 's' : ''} selected
          </span>
          {selectionCount > 1 && (
            <span className="text-muted-foreground">
              {sortedSel[0] + 1}–{sortedSel[sortedSel.length - 1] + 1} of {chunks.length}
            </span>
          )}
          <Button
            size="sm"
            variant="ghost"
            className="h-6 gap-1 px-2 text-xs text-primary/80 hover:text-primary"
            onClick={copySelection}
          >
            {copyDone
              ? <><Check className="h-3 w-3" /> Copied</>
              : <><Bot className="h-3 w-3" /> Copy with context</>
            }
          </Button>
          {onTranslateChunk && (
            <Button
              size="sm"
              variant="ghost"
              className="h-6 gap-1 px-2 text-xs text-primary/80 hover:text-primary"
              onClick={translateSelected}
              disabled={isTranslatingAny}
            >
              {isTranslatingAny
                ? <><Loader2 className="h-3 w-3 animate-spin" /> Translating…</>
                : <><Languages className="h-3 w-3" /> Translate {selectionCount > 1 ? `${selectionCount} chunks` : 'chunk'}</>
              }
            </Button>
          )}
          <button
            onClick={clearSelection}
            className="ml-auto rounded p-0.5 text-muted-foreground hover:text-foreground"
            title="Deselect all"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {/* ── Hint (first load) ─────────────────────────────────────────────── */}
      {selectionCount === 0 && dirtyCount === 0 && (
        <div className="shrink-0 border-b px-4 py-1.5 text-xs text-muted-foreground/60">
          Click to select · Shift+click to select a range · Hover a chunk for edit / copy actions
        </div>
      )}

      {/* ── Chunk list ────────────────────────────────────────────────────── */}
      <div className="flex-1 space-y-0.5 overflow-y-auto px-4 py-3">
        {chunks.map((chunk) => (
          <ChunkItem
            key={chunk.index}
            index={chunk.index}
            total={chunks.length}
            text={chunk.text}
            isDirty={chunk.isDirty}
            originalText={chunk.original}
            prevText={chunk.index > 0 ? chunks[chunk.index - 1].text : undefined}
            nextText={chunk.index < chunks.length - 1 ? chunks[chunk.index + 1].text : undefined}
            isSelected={selectedIndices.has(chunk.index)}
            isTranslating={translatingIndices.has(chunk.index)}
            onSelect={(shiftKey) => handleSelect(chunk.index, shiftKey)}
            onEdit={(value) => applyEdit(chunk.index, value)}
            onReset={() => resetEdit(chunk.index)}
            onTranslate={onTranslateChunk ? () => translateChunk(chunk.index) : undefined}
          />
        ))}
      </div>
    </div>
  );
}
