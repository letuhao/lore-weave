import { useEffect, useRef } from 'react';
import type { UIMessage } from '@ai-sdk/react';
import { MessageBubble } from './MessageBubble';

interface MessageListProps {
  messages: UIMessage[];
  isStreaming: boolean;
}

export function MessageList({ messages, isStreaming }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length, messages[messages.length - 1]?.parts]);

  if (messages.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <p className="text-sm text-muted-foreground">Send a message to start chatting.</p>
      </div>
    );
  }

  return (
    <div className="flex-1 space-y-4 overflow-y-auto px-6 py-4">
      {messages.map((msg, i) => {
        const isLast = i === messages.length - 1;
        return (
          <MessageBubble
            key={msg.id}
            message={msg}
            isLastAssistant={isLast && msg.role === 'assistant'}
            isStreaming={isStreaming}
          />
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
}
