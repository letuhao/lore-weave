import { useEffect, useRef, useState } from 'react';
import { Bot, Check, Copy, Pencil, RotateCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface ChunkItemProps {
  index: number;
  total: number;
  text: string;
  isDirty: boolean;
  originalText: string;
  /** Text of the preceding chunk — included in "Copy with context" for AI. */
  prevText: string | undefined;
  /** Text of the following chunk — included in "Copy with context" for AI. */
  nextText: string | undefined;
  isSelected: boolean;
  onSelect: () => void;
  onEdit: (value: string) => void;
  onReset: () => void;
}

/**
 * Single paragraph chunk — three interaction modes:
 *
 *  idle    → hover reveals action bar (Copy / Copy-with-context / Edit / Reset)
 *  editing → inline textarea with Accept / Discard controls
 *  copied  → brief check-mark flash on the relevant copy button
 *
 * Dirty chunks receive an amber left-border and background tint so the user can
 * see at a glance which chunks have been modified.
 */
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

  // Auto-grow textarea on mount
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

  /**
   * Builds a context-rich block for pasting into an AI agent:
   *
   *   [Chunk 3 of 47]
   *
   *   [Previous]
   *   ...prev paragraph...
   *
   *   [Current]
   *   ...this paragraph...
   *
   *   [Following]
   *   ...next paragraph...
   */
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

  return (
    <div
      onClick={() => { if (!isEditing) onSelect(); }}
      className={[
        'group relative rounded-md border transition-colors',
        isDirty
          ? 'border-amber-300 bg-amber-50/40 dark:border-amber-700/50 dark:bg-amber-900/10'
          : isSelected
          ? 'border-border bg-muted/30'
          : 'border-transparent hover:border-border',
      ].join(' ')}
    >
      {/* Dirty stripe */}
      {isDirty && (
        <div className="absolute inset-y-0 left-0 w-0.5 rounded-l-md bg-amber-400 dark:bg-amber-500" />
      )}

      {/* Chunk index — subtle, top-left */}
      <span className="absolute left-2 top-2.5 select-none font-mono text-[10px] tabular-nums text-muted-foreground/35">
        {index + 1}
      </span>

      <div className="px-6 py-3">
        {isEditing ? (
          /* ── Edit mode ──────────────────────────────────────────────────── */
          <div className="space-y-2">
            <textarea
              ref={textareaRef}
              value={editValue}
              onChange={(e) => {
                setEditValue(e.target.value);
                // auto-grow
                e.currentTarget.style.height = 'auto';
                e.currentTarget.style.height = `${e.currentTarget.scrollHeight}px`;
              }}
              onKeyDown={(e) => {
                if (e.key === 'Escape') discardEdit();
              }}
              className="w-full resize-none overflow-hidden rounded border border-input bg-background px-3 py-2 text-sm leading-relaxed focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              rows={Math.max(3, editValue.split('\n').length)}
            />
            <div className="flex items-center gap-2">
              <Button size="sm" onClick={acceptEdit} className="h-7 px-2.5 text-xs">
                Accept
              </Button>
              <Button size="sm" variant="ghost" onClick={discardEdit} className="h-7 px-2.5 text-xs">
                Discard
              </Button>
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
          /* ── Read mode ──────────────────────────────────────────────────── */
          <p className="whitespace-pre-wrap text-sm leading-relaxed">{text}</p>
        )}
      </div>

      {/* Hover action bar — hidden while editing */}
      {!isEditing && (
        <div className="absolute right-2 top-2 hidden items-center gap-0.5 rounded-md border bg-background shadow-sm group-hover:flex">
          {/* Copy chunk */}
          <button
            title="Copy chunk"
            onClick={(e) => { e.stopPropagation(); copyChunk(); }}
            className="rounded-l-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            {copied === 'chunk'
              ? <Check className="h-3.5 w-3.5 text-emerald-500" />
              : <Copy className="h-3.5 w-3.5" />}
          </button>

          {/* Copy with context (for AI agent) */}
          <button
            title={`Copy chunk ${index + 1} with surrounding context (prev + current + next)`}
            onClick={(e) => { e.stopPropagation(); copyWithContext(); }}
            className="border-l p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            {copied === 'context'
              ? <Check className="h-3.5 w-3.5 text-emerald-500" />
              : <Bot className="h-3.5 w-3.5" />}
          </button>

          {/* Edit */}
          <button
            title="Edit this chunk"
            onClick={(e) => { e.stopPropagation(); onSelect(); startEdit(); }}
            className="border-l p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <Pencil className="h-3.5 w-3.5" />
          </button>

          {/* Reset — only shown when dirty */}
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

      {/* Dirty label — bottom-right of chunk when not hovering */}
      {isDirty && !isEditing && (
        <span className="absolute bottom-1.5 right-2 text-[9px] text-amber-500/70 group-hover:hidden dark:text-amber-400/60">
          edited
        </span>
      )}
    </div>
  );
}
