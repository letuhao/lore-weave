import { useEffect, useRef, useState } from 'react';
import { Archive, Check, MessageSquare, Pencil, Trash2, X } from 'lucide-react';
import type { ChatSession } from '../types';

interface SessionItemProps {
  session: ChatSession;
  isActive: boolean;
  onSelect: () => void;
  onRename: (title: string) => void;
  onArchive: () => void;
  onDelete: () => void;
}

export function SessionItem({
  session,
  isActive,
  onSelect,
  onRename,
  onArchive,
  onDelete,
}: SessionItemProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState(session.title);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isEditing) inputRef.current?.select();
  }, [isEditing]);

  function commitRename() {
    const trimmed = editValue.trim();
    if (trimmed && trimmed !== session.title) onRename(trimmed);
    setIsEditing(false);
  }

  return (
    <div
      onClick={() => { if (!isEditing) onSelect(); }}
      className={[
        'group flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors',
        isActive ? 'bg-primary/10 text-primary' : 'hover:bg-muted/60 text-foreground',
      ].join(' ')}
    >
      <MessageSquare className="h-3.5 w-3.5 shrink-0 opacity-50" />

      {isEditing ? (
        <input
          ref={inputRef}
          value={editValue}
          onChange={(e) => setEditValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') commitRename();
            if (e.key === 'Escape') setIsEditing(false);
          }}
          onBlur={commitRename}
          onClick={(e) => e.stopPropagation()}
          className="min-w-0 flex-1 truncate bg-transparent text-sm focus:outline-none"
        />
      ) : (
        <span className="min-w-0 flex-1 truncate">{session.title}</span>
      )}

      {/* Hover actions */}
      {!isEditing && (
        <div className="hidden shrink-0 items-center gap-0.5 group-hover:flex">
          <button
            title="Rename"
            onClick={(e) => { e.stopPropagation(); setEditValue(session.title); setIsEditing(true); }}
            className="rounded p-0.5 text-muted-foreground hover:text-foreground"
          >
            <Pencil className="h-3 w-3" />
          </button>
          <button
            title="Archive"
            onClick={(e) => { e.stopPropagation(); onArchive(); }}
            className="rounded p-0.5 text-muted-foreground hover:text-foreground"
          >
            <Archive className="h-3 w-3" />
          </button>
          <button
            title="Delete"
            onClick={(e) => { e.stopPropagation(); onDelete(); }}
            className="rounded p-0.5 text-muted-foreground hover:text-destructive"
          >
            <Trash2 className="h-3 w-3" />
          </button>
        </div>
      )}

      {isEditing && (
        <div className="flex shrink-0 items-center gap-0.5">
          <button onClick={(e) => { e.stopPropagation(); commitRename(); }} className="rounded p-0.5 text-emerald-500">
            <Check className="h-3 w-3" />
          </button>
          <button onClick={(e) => { e.stopPropagation(); setIsEditing(false); }} className="rounded p-0.5 text-muted-foreground">
            <X className="h-3 w-3" />
          </button>
        </div>
      )}
    </div>
  );
}
