import { useState, useRef, useEffect } from 'react';
import { Check, Pencil, X } from 'lucide-react';
import { Button } from '@/components/ui/button';

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
          className="w-full resize-none rounded-md border bg-background/80 px-2 py-1.5 text-sm leading-relaxed text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
        />
        <div className="flex gap-1 justify-end">
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="h-6 w-6 p-0"
            onClick={cancelEdit}
            title="Cancel (Esc)"
          >
            <X className="h-3 w-3" />
          </Button>
          <Button
            type="button"
            size="sm"
            className="h-6 w-6 p-0"
            onClick={confirmEdit}
            title="Confirm (Enter)"
          >
            <Check className="h-3 w-3" />
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="group relative">
      <p className="whitespace-pre-wrap text-sm leading-relaxed">{content}</p>
      {onEdit && !disabled && (
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="absolute -bottom-1 -left-1 h-5 w-5 p-0 opacity-0 transition-opacity group-hover:opacity-70 hover:!opacity-100"
          onClick={startEdit}
          title="Edit message"
        >
          <Pencil className="h-3 w-3" />
        </Button>
      )}
    </div>
  );
}
