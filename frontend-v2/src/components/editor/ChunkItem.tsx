import { useRef, useEffect, useState } from 'react';
import { Languages, MessageCircle, Copy, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { type GrammarMatch, decorateText, escapeHtml } from '@/features/grammar/api';

interface ChunkItemProps {
  index: number;
  text: string;
  selected: boolean;
  autoFocus?: boolean;
  grammarMatches?: GrammarMatch[];
  onSelect: (index: number, shift: boolean) => void;
  onChange: (index: number, text: string) => void;
  onDelete: (index: number) => void;
  onBlurGrammar?: (index: number, text: string) => void;
}

export function ChunkItem({
  index, text, selected, autoFocus, grammarMatches,
  onSelect, onChange, onDelete, onBlurGrammar,
}: ChunkItemProps) {
  const editRef = useRef<HTMLDivElement>(null);
  const [focused, setFocused] = useState(false);

  // Focus newly inserted empty chunks
  useEffect(() => {
    if (autoFocus && editRef.current) {
      editRef.current.focus();
      const range = document.createRange();
      const sel = window.getSelection();
      range.selectNodeContents(editRef.current);
      range.collapse(false);
      sel?.removeAllRanges();
      sel?.addRange(range);
    }
  }, [autoFocus]);

  // Apply grammar decorations via ref when not focused
  useEffect(() => {
    if (!editRef.current || focused) return;
    editRef.current.innerHTML =
      grammarMatches?.length ? decorateText(text, grammarMatches) : escapeHtml(text);
  }, [text, grammarMatches, focused]);

  return (
    <div
      className={cn(
        'group flex gap-3 rounded-md border py-2 pl-3 pr-2 transition-colors',
        selected
          ? 'border-primary/40 bg-primary/[0.04]'
          : 'border-border/40 hover:border-border hover:bg-card',
      )}
      onClick={(e) => {
        if (e.target === e.currentTarget) onSelect(index, e.shiftKey);
      }}
    >
      {/* Chunk number */}
      <span
        className="w-5 flex-shrink-0 cursor-pointer pt-1 text-right font-mono text-[10px] text-muted-foreground/40 group-hover:text-muted-foreground"
        onClick={(e) => { e.stopPropagation(); onSelect(index, e.shiftKey); }}
        title="Click to select chunk"
      >
        {index + 1}
      </span>

      {/* Editable text */}
      <div
        ref={editRef}
        className={cn(
          'flex-1 text-sm leading-[1.8] outline-none',
          !text && 'before:text-muted-foreground/30 before:content-[attr(data-placeholder)]',
        )}
        style={{ whiteSpace: 'pre-wrap' }}
        data-placeholder="Empty paragraph — start typing..."
        contentEditable
        suppressContentEditableWarning
        onFocus={() => {
          setFocused(true);
          // Strip grammar decorations for clean editing
          if (editRef.current && grammarMatches?.length) {
            // Save cursor position
            const sel = window.getSelection();
            const cursorOffset = sel?.focusOffset ?? 0;
            editRef.current.innerHTML = escapeHtml(text);
            // Restore cursor (best-effort)
            try {
              const range = document.createRange();
              const node = editRef.current.firstChild;
              if (node) {
                range.setStart(node, Math.min(cursorOffset, node.textContent?.length ?? 0));
                range.collapse(true);
                sel?.removeAllRanges();
                sel?.addRange(range);
              }
            } catch { /* cursor restore is best-effort */ }
          }
        }}
        onBlur={(e) => {
          setFocused(false);
          const newText = e.currentTarget.innerText;
          onChange(index, newText);
          onBlurGrammar?.(index, newText);
        }}
      />

      {/* Action buttons */}
      <div className="flex flex-shrink-0 flex-col gap-1 pt-1 opacity-0 transition-opacity group-hover:opacity-60">
        <button
          className="rounded p-1 text-muted-foreground hover:bg-secondary hover:text-foreground"
          title="Translate chunk"
          onClick={(e) => e.stopPropagation()}
        >
          <Languages className="h-3 w-3" />
        </button>
        <button
          className="rounded p-1 text-muted-foreground hover:bg-secondary hover:text-foreground"
          title="Send to AI"
          onClick={(e) => e.stopPropagation()}
        >
          <MessageCircle className="h-3 w-3" />
        </button>
        <button
          className="rounded p-1 text-muted-foreground hover:bg-secondary hover:text-foreground"
          title="Copy"
          onClick={(e) => { e.stopPropagation(); void navigator.clipboard.writeText(text); }}
        >
          <Copy className="h-3 w-3" />
        </button>
        <div className="mx-1 my-0.5 border-t border-border/50" />
        <button
          className="rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
          title="Delete this chunk"
          onClick={(e) => { e.stopPropagation(); onDelete(index); }}
        >
          <Trash2 className="h-3 w-3" />
        </button>
      </div>
    </div>
  );
}
