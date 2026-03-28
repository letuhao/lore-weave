import { useState } from 'react';
import { RotateCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useChunks } from './useChunks';
import { ChunkItem } from './ChunkItem';

interface ChunkEditorProps {
  /** Source text — updated externally (e.g. on initial API load). */
  text: string;
  /** Called whenever any chunk edit is accepted, with the fully reassembled text. */
  onChange: (value: string) => void;
}

/**
 * Chunk-based view of a text document.
 *
 * Paragraphs are rendered as individually addressable chunks. Each chunk can be:
 *  - Copied as plain text
 *  - Copied with surrounding context (prev + current + next) for pasting into an AI agent
 *  - Edited inline — the edit is merged back into the full text via `onChange`
 *  - Reset to its original value
 *
 * Position and sibling awareness is built in: the chunk index (1-of-N) and the
 * surrounding paragraphs are always available, giving AI agents the context they
 * need to understand where in the document a passage sits.
 */
export function ChunkEditor({ text, onChange }: ChunkEditorProps) {
  const { chunks, dirtyCount, applyEdit, resetEdit, resetAll } = useChunks(text, onChange);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);

  if (chunks.length === 0) {
    return (
      <div className="flex h-full items-center justify-center p-8 text-sm text-muted-foreground">
        No paragraphs to display. Write something in editor mode first.
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* ── Dirty summary bar ─────────────────────────────────────────────── */}
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
          <span className="ml-auto text-muted-foreground/60">
            Save draft to persist changes
          </span>
        </div>
      )}

      {/* ── Chunk list ────────────────────────────────────────────────────── */}
      <div className="flex-1 space-y-1 overflow-y-auto px-4 py-3">
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
            isSelected={selectedIndex === chunk.index}
            onSelect={() => setSelectedIndex(chunk.index)}
            onEdit={(value) => applyEdit(chunk.index, value)}
            onReset={() => resetEdit(chunk.index)}
          />
        ))}
      </div>
    </div>
  );
}
