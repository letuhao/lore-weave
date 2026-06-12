import { useState, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Check, Pencil, Trash2, X } from 'lucide-react';
import TextareaAutosize from 'react-textarea-autosize';

interface UserMessageProps {
  content: string;
  onEdit?: (newContent: string) => void;
  onDelete?: () => void;
  disabled?: boolean;
}

export function UserMessage({ content, onEdit, onDelete, disabled }: UserMessageProps) {
  const { t } = useTranslation('chat');
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
      <div className="space-y-2">
        <TextareaAutosize
          ref={textareaRef as any}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              confirmEdit();
            }
            if (e.key === 'Escape') cancelEdit();
          }}
          minRows={3}
          maxRows={16}
          className="w-full resize-none rounded-md border border-ring bg-background px-3 py-2.5 text-sm leading-relaxed text-foreground focus:outline-none focus:ring-1 focus:ring-ring/50 shadow-[0_0_0_3px_rgba(212,149,42,0.1)]"
        />
        <div className="flex items-center justify-between">
          <span className="text-[10px] text-muted-foreground">
            {t('message.edit_hint')}
          </span>
          <div className="flex gap-1">
            <button
              type="button"
              onClick={cancelEdit}
              title={t('message.cancel_title')}
              className="rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
            >
              {t('message.cancel')}
            </button>
            <button
              type="button"
              onClick={confirmEdit}
              title={t('message.confirm_title')}
              className="rounded-md bg-accent/10 px-2 py-1 text-xs text-accent hover:bg-accent/20 transition-colors"
            >
              {t('message.save')}
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="group relative">
      <p className="whitespace-pre-wrap text-sm leading-relaxed">{content}</p>
      {!disabled && (onEdit || onDelete) && (
        <div className="absolute -bottom-1 -right-1 flex gap-0.5 opacity-0 transition-opacity group-hover:opacity-70 hover:!opacity-100 max-md:opacity-70">
          {onEdit && (
            <button
              type="button"
              onClick={startEdit}
              title={t('message.edit_message')}
              className="rounded-md p-1 text-muted-foreground hover:text-foreground"
            >
              <Pencil className="h-3 w-3" />
            </button>
          )}
          {onDelete && (
            <button
              type="button"
              onClick={onDelete}
              title={t('message.delete_message')}
              className="rounded-md p-1 text-muted-foreground hover:text-destructive"
            >
              <Trash2 className="h-3 w-3" />
            </button>
          )}
        </div>
      )}
    </div>
  );
}
