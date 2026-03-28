import { useEffect, useRef, useState } from 'react';
import { Bot, Check, Copy, Pencil, RotateCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface ChunkItemProps {
  index: number;
  total: number;
  text: string;
  isDirty: boolean;
  originalText: string;
  prevText: string | undefined;
  nextText: string | undefined;
  isSelected: boolean;
  /** shiftKey = true triggers range selection in the parent */
  onSelect: (shiftKey: boolean) => void;
  onEdit: (value: string) => void;
  onReset: () => void;
}

export function ChunkItem({
  index,
  total,
  text,
  isDirty,
  originalText,
  prevText,
  nextText,
  isSelected,
  onSelect,
  onEdit,
  onReset,
}: ChunkItemProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState('');
  const [copied, setCopied] = useState<'chunk' | 'context' | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (isEditing && textareaRef.current) {
      const el = textareaRef.current;
      el.style.height = 'auto';
      el.style.height = `${el.scrollHeight}px`;
      el.focus();
      el.selectionStart = el.value.length;
    }
  }, [isEditing]);

  function startEdit() {
    setEditValue(text);
    setIsEditing(true);
  }

  function acceptEdit() {
    onEdit(editValue);
    setIsEditing(false);
  }

  function discardEdit() {
    setIsEditing(false);
  }

  function copyChunk() {
    void navigator.clipboard.writeText(text).then(() => {
      setCopied('chunk');
      setTimeout(() => setCopied(null), 1500);
    });
  }

  function copyWithContext() {
    const parts: string[] = [`[Chunk ${index + 1} of ${total}]`];
    if (prevText) parts.push(`\n[Previous]\n${prevText}`);
    parts.push(`\n[Current]\n${text}`);
    if (nextText) parts.push(`\n[Following]\n${nextText}`);
    void navigator.clipboard.writeText(parts.join('\n')).then(() => {
      setCopied('context');
      setTimeout(() => setCopied(null), 1500);
    });
  }

  // Derive border + bg from selection/dirty state
  const containerClass = [
    'group relative flex cursor-pointer rounded-md border transition-colors select-none',
    isSelected
      ? 'border-primary/40 bg-primary/5 dark:bg-primary/10'
      : isDirty
      ? 'border-amber-200 bg-amber-50/40 dark:border-amber-700/40 dark:bg-amber-900/10'
      : 'border-transparent hover:border-border',
  ].join(' ');

  return (
    <div
      onClick={(e) => { if (!isEditing) onSelect(e.shiftKey); }}
      className={containerClass}
    >
      {/* Amber dirty stripe — absolute on left edge, always shown when dirty */}
      {isDirty && (
        <div className="absolute inset-y-0 left-0 w-0.5 rounded-l-md bg-amber-400 dark:bg-amber-500" />
      )}

      {/* ── Left gutter: chunk number ──────────────────────────────────────── */}
      <div className="flex w-10 shrink-0 flex-col items-center gap-1 pt-3 pb-2">
        <span
          className={[
            'font-mono text-xs tabular-nums font-medium transition-colors',
            isSelected ? 'text-primary' : 'text-muted-foreground/50',
          ].join(' ')}
        >
          {index + 1}
        </span>
        {/* Selection dot */}
        {isSelected && (
          <div className="h-1 w-1 rounded-full bg-primary/60" />
        )}
      </div>

      {/* ── Content ────────────────────────────────────────────────────────── */}
      <div className="min-w-0 flex-1 py-3 pr-10">
        {isEditing ? (
          <div className="space-y-2" onClick={(e) => e.stopPropagation()}>
            <textarea
              ref={textareaRef}
              value={editValue}
              onChange={(e) => {
                setEditValue(e.target.value);
                e.currentTarget.style.height = 'auto';
                e.currentTarget.style.height = `${e.currentTarget.scrollHeight}px`;
              }}
              onKeyDown={(e) => { if (e.key === 'Escape') discardEdit(); }}
              className="w-full resize-none overflow-hidden rounded border border-input bg-background px-3 py-2 text-sm leading-relaxed focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              rows={Math.max(3, editValue.split('\n').length)}
            />
            <div className="flex items-center gap-2">
              <Button size="sm" onClick={acceptEdit} className="h-7 px-2.5 text-xs">Accept</Button>
              <Button size="sm" variant="ghost" onClick={discardEdit} className="h-7 px-2.5 text-xs">Discard</Button>
              {isDirty && (
                <button
                  onClick={() => { onReset(); setIsEditing(false); }}
                  className="ml-auto text-xs text-muted-foreground hover:text-foreground"
                >
                  Reset to original
                </button>
              )}
            </div>
          </div>
        ) : (
          <p className="whitespace-pre-wrap text-sm leading-relaxed">{text}</p>
        )}
      </div>

      {/* ── Hover action bar ───────────────────────────────────────────────── */}
      {!isEditing && (
        <div className="absolute right-2 top-2 hidden items-center gap-0.5 rounded-md border bg-background shadow-sm group-hover:flex">
          <button
            title="Copy chunk"
            onClick={(e) => { e.stopPropagation(); copyChunk(); }}
            className="rounded-l-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            {copied === 'chunk' ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}
          </button>
          <button
            title={`Copy chunk ${index + 1} with surrounding context`}
            onClick={(e) => { e.stopPropagation(); copyWithContext(); }}
            className="border-l p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            {copied === 'context' ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Bot className="h-3.5 w-3.5" />}
          </button>
          <button
            title="Edit this chunk"
            onClick={(e) => { e.stopPropagation(); onSelect(false); startEdit(); }}
            className="border-l p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <Pencil className="h-3.5 w-3.5" />
          </button>
          {isDirty && (
            <button
              title="Reset to original"
              onClick={(e) => { e.stopPropagation(); onReset(); }}
              className="rounded-r-md border-l p-1.5 text-muted-foreground hover:bg-muted hover:text-destructive"
            >
              <RotateCcw className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      )}

      {/* Dirty label — visible at rest, hidden on hover (action bar takes over) */}
      {isDirty && !isEditing && (
        <span className="absolute bottom-1.5 right-2 text-[9px] text-amber-500/70 group-hover:hidden dark:text-amber-400/60">
          edited
        </span>
      )}
    </div>
  );
}
