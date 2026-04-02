import { useEffect, useRef } from 'react';
import { MessageBubble } from './MessageBubble';
import type { ChatMessage } from '../types';

interface MessageListProps {
  messages: ChatMessage[];
  /** Partial streaming text for in-progress response */
  streamingText: string;
  isStreaming: boolean;
  onEditMessage?: (content: string, sequenceNum: number) => void;
  onRegenerateMessage?: (userContent: string, userSequenceNum: number) => void;
  disabled?: boolean;
}

export function MessageList({
  messages,
  streamingText,
  isStreaming,
  onEditMessage,
  onRegenerateMessage,
  disabled,
}: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll on new messages or streaming text
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length, streamingText]);

  if (messages.length === 0 && !isStreaming) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <p className="text-sm text-muted-foreground">Send a message to start chatting.</p>
      </div>
    );
  }

  // Find the last user message for regeneration context
  function findPrecedingUser(index: number): { content: string; sequenceNum: number } | null {
    for (let i = index - 1; i >= 0; i--) {
      if (messages[i].role === 'user') {
        return { content: messages[i].content, sequenceNum: messages[i].sequence_num };
      }
    }
    return null;
  }

  return (
    <div className="flex-1 overflow-y-auto px-8 py-6">
      <div className="mx-auto flex max-w-[720px] flex-col gap-5">
        {messages.map((msg, i) => (
          <MessageBubble
            key={msg.message_id}
            message={msg}
            onEdit={
              msg.role === 'user' && onEditMessage
                ? (newContent: string) => onEditMessage(newContent, msg.sequence_num)
                : undefined
            }
            onRegenerate={
              msg.role === 'assistant' && onRegenerateMessage
                ? () => {
                    const user = findPrecedingUser(i);
                    if (user) onRegenerateMessage(user.content, user.sequenceNum);
                  }
                : undefined
            }
            disabled={disabled}
          />
        ))}

        {/* Streaming assistant message (in progress) */}
        {isStreaming && streamingText && (
          <MessageBubble
            message={{
              message_id: `streaming-${Date.now()}`,
              session_id: '',
              owner_user_id: '',
              role: 'assistant',
              content: streamingText,
              content_parts: null,
              sequence_num: -1,
              input_tokens: null,
              output_tokens: null,
              model_ref: null,
              is_error: false,
              error_detail: null,
              parent_message_id: null,
              created_at: new Date().toISOString(),
            }}
            isStreamingMsg
            disabled
          />
        )}

        {/* Typing indicator (before any text arrives) */}
        {isStreaming && !streamingText && (
          <div className="flex justify-start">
            <div className="flex items-center gap-1.5 rounded-[12px_12px_12px_4px] border border-border bg-card px-4 py-3">
              <span className="inline-block h-1.5 w-1.5 animate-[typing-dot_1.4s_infinite_0s] rounded-full bg-accent" />
              <span className="inline-block h-1.5 w-1.5 animate-[typing-dot_1.4s_infinite_0.2s] rounded-full bg-accent" />
              <span className="inline-block h-1.5 w-1.5 animate-[typing-dot_1.4s_infinite_0.4s] rounded-full bg-accent" />
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  );
}
