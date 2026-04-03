import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Archive,
  Check,
  MessageSquare,
  Pencil,
  Pin,
  PinOff,
  Plus,
  Search,
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
  onTogglePin: () => void;
}

function SessionItem({
  session,
  isActive,
  modelNameMap,
  onSelect,
  onRename,
  onArchive,
  onDelete,
  onTogglePin,
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
          <div className="flex items-center gap-1">
            <p
              className={cn(
                'truncate text-[13px] font-medium flex-1',
                isActive ? 'text-foreground' : 'text-muted-foreground',
              )}
            >
              {session.title}
            </p>
            {session.is_pinned && <Pin className="h-2.5 w-2.5 shrink-0 text-primary" />}
          </div>
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
            title={session.is_pinned ? 'Unpin' : 'Pin'}
            onClick={(e) => { e.stopPropagation(); onTogglePin(); }}
            className="rounded p-0.5 text-muted-foreground hover:text-primary"
          >
            {session.is_pinned ? <PinOff className="h-3 w-3" /> : <Pin className="h-3 w-3" />}
          </button>
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
  onTogglePin?: (sessionId: string, pinned: boolean) => void;
}

// ── Temporal grouping ──────────────────────────────────────────────────────────

type SessionGroup = { label: string; sessions: ChatSession[] };

function groupSessions(sessions: ChatSession[]): SessionGroup[] {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - 86_400_000);
  const weekAgo = new Date(today.getTime() - 7 * 86_400_000);

  const pinned: ChatSession[] = [];
  const todayArr: ChatSession[] = [];
  const yesterdayArr: ChatSession[] = [];
  const weekArr: ChatSession[] = [];
  const older: ChatSession[] = [];

  for (const s of sessions) {
    if (s.is_pinned) { pinned.push(s); continue; }
    const d = new Date(s.last_message_at ?? s.created_at);
    if (d >= today) todayArr.push(s);
    else if (d >= yesterday) yesterdayArr.push(s);
    else if (d >= weekAgo) weekArr.push(s);
    else older.push(s);
  }

  const groups: SessionGroup[] = [];
  if (pinned.length) groups.push({ label: 'Pinned', sessions: pinned });
  if (todayArr.length) groups.push({ label: 'Today', sessions: todayArr });
  if (yesterdayArr.length) groups.push({ label: 'Yesterday', sessions: yesterdayArr });
  if (weekArr.length) groups.push({ label: 'This Week', sessions: weekArr });
  if (older.length) groups.push({ label: 'Older', sessions: older });
  return groups;
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
  onTogglePin,
}: SessionSidebarProps) {
  const [search, setSearch] = useState('');

  const filtered = useMemo(() => {
    if (!search.trim()) return sessions;
    const q = search.toLowerCase();
    return sessions.filter((s) => s.title.toLowerCase().includes(q));
  }, [sessions, search]);

  const groups = useMemo(() => groupSessions(filtered), [filtered]);

  return (
    <div className="flex h-full w-[270px] shrink-0 flex-col border-r border-border bg-card">
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

      {/* Search */}
      <div className="px-3 py-2">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search conversations..."
            className="w-full rounded-md border border-border bg-background py-1.5 pl-7 pr-2 text-xs text-foreground placeholder:text-muted-foreground outline-none focus:border-ring"
          />
        </div>
      </div>

      {/* Session list with groups */}
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

        {!isLoading && filtered.length === 0 && sessions.length > 0 && (
          <p className="mt-6 px-4 text-center text-xs text-muted-foreground">
            No matches for &ldquo;{search}&rdquo;
          </p>
        )}

        {groups.map((group) => (
          <div key={group.label}>
            <p className="px-4 pb-1 pt-3 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              {group.label === 'Pinned' && <Pin className="mr-1 inline h-2.5 w-2.5 text-primary" />}
              {group.label}
            </p>
            {group.sessions.map((s) => (
              <SessionItem
                key={s.session_id}
                session={s}
                isActive={s.session_id === activeSessionId}
                modelNameMap={modelNameMap}
                onSelect={() => onSelect(s)}
                onRename={(title) => onRename(s.session_id, title)}
                onArchive={() => onArchive(s.session_id)}
                onDelete={() => onDelete(s.session_id)}
                onTogglePin={() => onTogglePin?.(s.session_id, !s.is_pinned)}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
