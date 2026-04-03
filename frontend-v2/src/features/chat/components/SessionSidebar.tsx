import { useEffect, useRef, useState } from 'react';
import {
  Archive,
  Check,
  MessageSquare,
  Pencil,
  Plus,
  Trash2,
  X,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ChatSession } from '../types';

// ── SessionItem ─────────────────────────────────────────────────────────────────

interface SessionItemProps {
  session: ChatSession;
  isActive: boolean;
  modelNameMap?: Map<string, string>;
  onSelect: () => void;
  onRename: (title: string) => void;
  onArchive: () => void;
  onDelete: () => void;
}

function SessionItem({
  session,
  isActive,
  modelNameMap,
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

  // Relative time helper
  function relativeTime(iso: string | null): string {
    if (!iso) return '';
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'Just now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    const days = Math.floor(hrs / 24);
    if (days === 1) return 'Yesterday';
    return `${days}d ago`;
  }

  return (
    <div
      onClick={() => { if (!isEditing) onSelect(); }}
      className={cn(
        'group cursor-pointer border-l-2 px-4 py-3 transition-colors',
        isActive
          ? 'border-l-accent bg-accent/5'
          : 'border-l-transparent hover:bg-card-foreground/5',
      )}
    >
      {isEditing ? (
        <div className="flex items-center gap-1">
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
            className="min-w-0 flex-1 truncate bg-transparent text-[13px] font-medium focus:outline-none"
          />
          <button
            onClick={(e) => { e.stopPropagation(); commitRename(); }}
            className="rounded p-0.5 text-emerald-400"
          >
            <Check className="h-3 w-3" />
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); setIsEditing(false); }}
            className="rounded p-0.5 text-muted-foreground"
          >
            <X className="h-3 w-3" />
          </button>
        </div>
      ) : (
        <>
          <p
            className={cn(
              'truncate text-[13px] font-medium',
              isActive ? 'text-foreground' : 'text-muted-foreground',
            )}
          >
            {session.title}
          </p>
          <div className="mt-1 flex items-center justify-between">
            <span className="text-[10px] text-muted-foreground">
              {modelNameMap?.get(session.model_ref) ?? (session.model_source === 'user_model' ? 'My Model' : 'Platform')}
            </span>
            <span className="text-[10px] text-muted-foreground">
              {relativeTime(session.last_message_at ?? session.created_at)}
            </span>
          </div>
        </>
      )}

      {/* Hover actions */}
      {!isEditing && (
        <div className="mt-1 hidden items-center gap-1 group-hover:flex">
          <button
            title="Rename"
            onClick={(e) => {
              e.stopPropagation();
              setEditValue(session.title);
              setIsEditing(true);
            }}
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
    </div>
  );
}

// ── SessionSidebar ──────────────────────────────────────────────────────────────

interface SessionSidebarProps {
  sessions: ChatSession[];
  activeSessionId: string | null;
  isLoading: boolean;
  modelNameMap?: Map<string, string>;
  onSelect: (session: ChatSession) => void;
  onCreate: () => void;
  onRename: (sessionId: string, title: string) => void;
  onArchive: (sessionId: string) => void;
  onDelete: (sessionId: string) => void;
}

export function SessionSidebar({
  sessions,
  activeSessionId,
  isLoading,
  modelNameMap,
  onSelect,
  onCreate,
  onRename,
  onArchive,
  onDelete,
}: SessionSidebarProps) {
  return (
    <div className="flex h-full w-[260px] shrink-0 flex-col border-r border-border bg-card">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <span className="text-[13px] font-semibold text-foreground">Conversations</span>
        <button
          type="button"
          onClick={onCreate}
          className="inline-flex items-center gap-1 rounded-md bg-accent px-2.5 py-1 text-[11px] font-medium text-accent-foreground transition-colors hover:bg-accent/90"
        >
          <Plus className="h-3 w-3" />
          New
        </button>
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto">
        {isLoading && sessions.length === 0 && (
          <div className="space-y-3 px-4 py-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="animate-pulse space-y-1">
                <div className="h-3 w-3/4 rounded bg-muted" />
                <div className="h-2 w-1/2 rounded bg-muted" />
              </div>
            ))}
          </div>
        )}

        {!isLoading && sessions.length === 0 && (
          <p className="mt-6 px-4 text-center text-xs text-muted-foreground">
            No conversations yet.
            <br />
            Click <strong>New</strong> to start.
          </p>
        )}

        {sessions.map((s) => (
          <SessionItem
            key={s.session_id}
            session={s}
            isActive={s.session_id === activeSessionId}
            modelNameMap={modelNameMap}
            onSelect={() => onSelect(s)}
            onRename={(title) => onRename(s.session_id, title)}
            onArchive={() => onArchive(s.session_id)}
            onDelete={() => onDelete(s.session_id)}
          />
        ))}
      </div>
    </div>
  );
}
