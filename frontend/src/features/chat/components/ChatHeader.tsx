import { Bot, Download } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { chatApi } from '../api';
import type { ChatSession } from '../types';

interface ChatHeaderProps {
  session: ChatSession;
}

export function ChatHeader({ session }: ChatHeaderProps) {
  function handleExport(format: 'markdown' | 'json') {
    const url = chatApi.exportUrl(session.session_id, format);
    window.open(url, '_blank');
  }

  return (
    <div className="flex shrink-0 items-center gap-3 border-b px-6 py-3">
      <Bot className="h-4 w-4 text-muted-foreground" />
      <span className="text-sm font-medium">{session.title}</span>
      <Badge variant="outline" className="text-[10px]">
        {session.model_source === 'user_model' ? 'My Model' : 'Platform'}
      </Badge>
      {session.status === 'archived' && (
        <Badge variant="secondary" className="text-[10px]">Archived</Badge>
      )}
      <div className="ml-auto flex items-center gap-1">
        <Button
          size="sm"
          variant="ghost"
          className="h-7 gap-1.5 px-2 text-xs text-muted-foreground"
          onClick={() => handleExport('markdown')}
        >
          <Download className="h-3.5 w-3.5" />
          Export
        </Button>
      </div>
    </div>
  );
}
