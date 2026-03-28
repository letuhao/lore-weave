import { Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { ChatSession } from '../types';
import { SessionItem } from './SessionItem';

interface SessionSidebarProps {
  sessions: ChatSession[];
  activeSessionId: string | null;
  onSelect: (session: ChatSession) => void;
  onCreate: () => void;
  onRename: (sessionId: string, title: string) => void;
  onArchive: (sessionId: string) => void;
  onDelete: (sessionId: string) => void;
}

export function SessionSidebar({
  sessions,
  activeSessionId,
  onSelect,
  onCreate,
  onRename,
  onArchive,
  onDelete,
}: SessionSidebarProps) {
  return (
    <div className="flex h-full w-56 shrink-0 flex-col border-r bg-muted/20">
      <div className="flex items-center justify-between border-b px-3 py-2">
        <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Chats
        </span>
        <Button
          size="sm"
          variant="ghost"
          className="h-6 w-6 p-0"
          title="New chat"
          onClick={onCreate}
        >
          <Plus className="h-3.5 w-3.5" />
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto px-1.5 py-1">
        {sessions.length === 0 && (
          <p className="mt-4 px-2 text-center text-xs text-muted-foreground">
            No chats yet. Click + to start.
          </p>
        )}
        {sessions.map((s) => (
          <SessionItem
            key={s.session_id}
            session={s}
            isActive={s.session_id === activeSessionId}
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
