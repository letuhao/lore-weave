import { toast } from 'sonner';
import type { ChatSession } from '../types';
import type { useChatMessages } from '../hooks/useChatMessages';
import { ChatHeader } from './ChatHeader';
import { ChatInputBar } from './ChatInputBar';
import { MessageList } from './MessageList';

interface ChatWindowProps {
  session: ChatSession;
  chat: ReturnType<typeof useChatMessages>;
  onRename?: () => void;
}

export function ChatWindow({ session, chat, onRename }: ChatWindowProps) {
  const isArchived = session.status === 'archived';

  function handleSend(content: string) {
    chat.send(content).catch((err) => {
      toast.error(`Chat error: ${(err as Error).message}`);
    });
  }

  function handleEdit(content: string, sequenceNum: number) {
    chat.edit(content, sequenceNum).catch((err) => {
      toast.error(`Edit failed: ${(err as Error).message}`);
    });
  }

  function handleRegenerate(userContent: string, userSequenceNum: number) {
    chat.regenerate(userContent, userSequenceNum).catch((err) => {
      toast.error(`Regenerate failed: ${(err as Error).message}`);
    });
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <ChatHeader session={session} onRename={onRename} />

      <MessageList
        messages={chat.messages}
        streamingText={chat.streamingText}
        isStreaming={chat.isStreaming}
        onEditMessage={!isArchived ? handleEdit : undefined}
        onRegenerateMessage={!isArchived ? handleRegenerate : undefined}
        disabled={isArchived || chat.isStreaming}
      />

      <ChatInputBar
        onSend={handleSend}
        onStop={chat.stop}
        isStreaming={chat.isStreaming}
        disabled={isArchived}
      />
    </div>
  );
}
