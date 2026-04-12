import { Menu, MessageSquareText } from 'lucide-react';
import { useChatSession } from '../providers';

interface ChatEmptyStateProps {
  className?: string;
}

export function ChatEmptyState({ className }: ChatEmptyStateProps) {
  const { setShowNewDialog, setMobileSidebarOpen } = useChatSession();

  return (
    <div className={`relative flex flex-1 flex-col items-center justify-center gap-4 text-center ${className ?? ''}`}>
      <button
        type="button"
        onClick={() => setMobileSidebarOpen(true)}
        className="absolute left-3 top-3 rounded-md p-2 text-muted-foreground hover:bg-muted md:hidden"
        aria-label="Open conversations"
      >
        <Menu className="h-5 w-5" />
      </button>
      <MessageSquareText className="h-12 w-12 text-muted-foreground/30" />
      <div>
        <p className="text-sm font-medium text-foreground">No chat selected</p>
        <p className="mt-1 text-xs text-muted-foreground">
          Select a conversation from the sidebar or start a new one.
        </p>
      </div>
      <button
        type="button"
        onClick={() => setShowNewDialog(true)}
        className="flex items-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-white hover:brightness-110"
      >
        Start New Chat
      </button>
    </div>
  );
}
