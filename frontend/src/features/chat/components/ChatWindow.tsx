import { useCallback, useState } from 'react';
import { DefaultChatTransport } from 'ai';
import { useChat } from '@ai-sdk/react';
import type { UIMessage } from '@ai-sdk/react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import type { ChatSession } from '../types';
import { useStreamingEdit } from '../hooks/useStreamingEdit';
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

  const { messages, sendMessage, setMessages, stop, status } = useChat({
    transport: new DefaultChatTransport({
      api: `${apiBase()}/v1/chat/sessions/${session.session_id}/messages`,
      headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
    }),
    onError(error: Error) {
      toast.error(`Chat error: ${error.message}`);
    },
  });

  const {
    streamingText,
    status: editStatus,
    sendEdit,
    regenerate,
    cancel: cancelEdit,
  } = useStreamingEdit();

  const isLoading = status === 'streaming' || status === 'submitted' || editStatus === 'streaming';
  const isArchived = session.status === 'archived';

  function handleSubmit() {
    const text = input.trim();
    if (!text || isLoading) return;
    setInput('');
    void sendMessage({ text });
  }

  /**
   * Edit a user message at `index` and re-run the conversation from that point.
   * We truncate local messages, then stream the new response manually.
   */
  const handleEditMessage = useCallback(
    async (index: number, newContent: string) => {
      if (isLoading) return;

      // Find the sequence number context: the message being edited is at `index`.
      // We keep messages [0..index-1] and replace from index onward.
      const truncated = messages.slice(0, index);
      const editSequence = index; // edit_from_sequence = messages before the edited one

      // Add the edited user message as a placeholder
      const editedUserMsg: UIMessage = {
        id: `edit-${Date.now()}`,
        role: 'user',
        parts: [{ type: 'text', text: newContent }],
        createdAt: new Date(),
      };
      setMessages([...truncated, editedUserMsg]);

      try {
        const finalText = await sendEdit(session.session_id, newContent, editSequence);

        // Append the assistant response
        const assistantMsg: UIMessage = {
          id: `regen-${Date.now()}`,
          role: 'assistant',
          parts: [{ type: 'text', text: finalText }],
          createdAt: new Date(),
        };
        setMessages([...truncated, editedUserMsg, assistantMsg]);
      } catch (err) {
        toast.error(`Edit failed: ${(err as Error).message}`);
      }
    },
    [messages, isLoading, sendEdit, setMessages, session.session_id],
  );

  /**
   * Regenerate an assistant message at `index`.
   * We find the preceding user message, truncate after it, and re-run.
   */
  const handleRegenerateMessage = useCallback(
    async (index: number) => {
      if (isLoading) return;

      // Find the user message that preceded this assistant message
      let userMsgIndex = index - 1;
      while (userMsgIndex >= 0 && messages[userMsgIndex].role !== 'user') {
        userMsgIndex--;
      }
      if (userMsgIndex < 0) {
        toast.error('No user message found to regenerate from');
        return;
      }

      const userMsg = messages[userMsgIndex];
      const userContent = userMsg.parts
        .filter((p) => p.type === 'text')
        .map((p) => (p as { type: 'text'; text: string }).text)
        .join('');

      // Keep messages up to and including the user message
      const truncated = messages.slice(0, userMsgIndex + 1);
      setMessages(truncated);

      const regenSequence = userMsgIndex + 1; // edit_from_sequence = the user message's position

      try {
        const finalText = await regenerate(session.session_id, userContent, regenSequence);

        const assistantMsg: UIMessage = {
          id: `regen-${Date.now()}`,
          role: 'assistant',
          parts: [{ type: 'text', text: finalText }],
          createdAt: new Date(),
        };
        setMessages([...truncated, assistantMsg]);
      } catch (err) {
        toast.error(`Regenerate failed: ${(err as Error).message}`);
      }
    },
    [messages, isLoading, regenerate, setMessages, session.session_id],
  );

  // Build display messages: if streaming an edit, show streaming text as last assistant msg
  const displayMessages =
    editStatus === 'streaming' && streamingText
      ? [
          ...messages,
          {
            id: `streaming-edit-${Date.now()}`,
            role: 'assistant' as const,
            parts: [{ type: 'text' as const, text: streamingText }],
            createdAt: new Date(),
          },
        ]
      : messages;

  return (
    <div className="flex h-full flex-col">
      <ChatHeader session={session} />

      <MessageList
        messages={displayMessages}
        isStreaming={status === 'streaming' || editStatus === 'streaming'}
        onEditMessage={handleEditMessage}
        onRegenerateMessage={handleRegenerateMessage}
        disabled={isArchived || isLoading}
      />

      <ChatInputBar
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onSubmit={handleSubmit}
        isLoading={isLoading}
        onStop={editStatus === 'streaming' ? cancelEdit : stop}
        disabled={isArchived}
      />
    </div>
  );
}
