import { useState } from 'react';
import { DefaultChatTransport } from 'ai';
import { useChat } from '@ai-sdk/react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import type { ChatSession } from '../types';
import { ChatHeader } from './ChatHeader';
import { ChatInputBar } from './ChatInputBar';
import { MessageList } from './MessageList';

const apiBase = () => import.meta.env.VITE_API_BASE || 'http://localhost:3000';

interface ChatWindowProps {
  session: ChatSession;
}

export function ChatWindow({ session }: ChatWindowProps) {
  const { accessToken } = useAuth();
  const [input, setInput] = useState('');

  const { messages, sendMessage, stop, status } = useChat({
    transport: new DefaultChatTransport({
      api: `${apiBase()}/v1/chat/sessions/${session.session_id}/messages`,
      headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
    }),
    onError(error: Error) {
      toast.error(`Chat error: ${error.message}`);
    },
  });

  const isLoading = status === 'streaming' || status === 'submitted';
  const isArchived = session.status === 'archived';

  function handleSubmit() {
    const text = input.trim();
    if (!text || isLoading) return;
    setInput('');
    void sendMessage({ text });
  }

  return (
    <div className="flex h-full flex-col">
      <ChatHeader session={session} />

      <MessageList messages={messages} isStreaming={status === 'streaming'} />

      <ChatInputBar
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onSubmit={handleSubmit}
        isLoading={isLoading}
        onStop={stop}
        disabled={isArchived}
      />
    </div>
  );
}
