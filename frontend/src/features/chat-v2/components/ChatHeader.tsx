import { Download, Pencil } from 'lucide-react';
import { chatApi } from '../api';
import type { ChatSession } from '../types';

interface ChatHeaderProps {
  session: ChatSession;
  onRename?: () => void;
}

export function ChatHeader({ session, onRename }: ChatHeaderProps) {
  function handleExport(format: 'markdown' | 'json') {
    const url = chatApi.exportUrl(session.session_id, format);
    window.open(url, '_blank');
  }

  return (
    <div className="flex shrink-0 items-center justify-between border-b border-border bg-card px-6 py-3">
      <div>
        <h2 className="text-sm font-semibold text-foreground">{session.title}</h2>
        <p className="mt-0.5 text-[11px] text-muted-foreground">
          {session.model_source === 'user_model' ? 'My Model' : 'Platform'} \u00B7{' '}
          {session.message_count} message{session.message_count !== 1 ? 's' : ''}
          {session.status === 'archived' && (
            <span className="ml-1.5 rounded bg-secondary px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
              Archived
            </span>
          )}
        </p>
      </div>
      <div className="flex items-center gap-1.5">
        <button
          type="button"
          onClick={() => handleExport('markdown')}
          title="Export"
          className="rounded-md p-1.5 text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
        >
          <Download className="h-[15px] w-[15px]" />
        </button>
        {onRename && (
          <button
            type="button"
            onClick={onRename}
            title="Rename"
            className="rounded-md p-1.5 text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
          >
            <Pencil className="h-[15px] w-[15px]" />
          </button>
        )}
      </div>
    </div>
  );
}
