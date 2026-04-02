import { useState, useRef, useEffect } from 'react';
import { Check, Pencil, X } from 'lucide-react';

interface UserMessageProps {
  content: string;
  onEdit?: (newContent: string) => void;
  disabled?: boolean;
}

export function UserMessage({ content, onEdit, disabled }: UserMessageProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(content);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (editing && textareaRef.current) {
      textareaRef.current.focus();
      textareaRef.current.selectionStart = textareaRef.current.value.length;
    }
  }, [editing]);

  function startEdit() {
    setDraft(content);
    setEditing(true);
  }

  function confirmEdit() {
    const trimmed = draft.trim();
    if (!trimmed || trimmed === content) {
      setEditing(false);
      return;
    }
    setEditing(false);
    onEdit?.(trimmed);
  }

  function cancelEdit() {
    setEditing(false);
    setDraft(content);
  }

  if (editing) {
    return (
      <div className="space-y-1.5">
        <textarea
          ref={textareaRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              confirmEdit();
            }
            if (e.key === 'Escape') cancelEdit();
          }}
          rows={Math.min(8, draft.split('\n').length + 1)}
          className="w-full resize-none rounded-md border border-border bg-background px-2.5 py-1.5 text-sm leading-relaxed text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
        />
        <div className="flex gap-1 justify-end">
          <button
            type="button"
            onClick={cancelEdit}
            title="Cancel (Esc)"
            className="rounded-md p-1 text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
          >
            <X className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={confirmEdit}
            title="Confirm (Enter)"
            className="rounded-md p-1 text-emerald-400 hover:bg-emerald-500/10 transition-colors"
          >
            <Check className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="group relative">
      <p className="whitespace-pre-wrap text-sm leading-relaxed">{content}</p>
      {onEdit && !disabled && (
        <button
          type="button"
          onClick={startEdit}
          title="Edit message"
          className="absolute -bottom-1 -right-1 rounded-md p-1 opacity-0 transition-opacity group-hover:opacity-70 hover:!opacity-100 text-muted-foreground hover:text-foreground"
        >
          <Pencil className="h-3 w-3" />
        </button>
      )}
    </div>
  );
}
