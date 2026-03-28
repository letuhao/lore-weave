import { Bot } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import type { ChatSession } from '../types';

interface ChatHeaderProps {
  session: ChatSession;
}

export function ChatHeader({ session }: ChatHeaderProps) {
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
    </div>
  );
}
