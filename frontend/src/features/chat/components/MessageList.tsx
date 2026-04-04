import { useEffect, useRef } from 'react';
import { MessageBubble } from './MessageBubble';
import type { ChatMessage } from '../types';

type StreamPhase = 'idle' | 'thinking' | 'responding';

interface MessageListProps {
  messages: ChatMessage[];
  /** Partial streaming text for in-progress response */
  streamingText: string;
  /** Partial streaming reasoning text */
  streamingReasoning?: string;
  /** Current stream phase */
  streamPhase?: StreamPhase;
  /** Elapsed thinking time in seconds */
  thinkingElapsed?: number;
  isStreaming: boolean;
  onEditMessage?: (content: string, sequenceNum: number) => void;
  onRegenerateMessage?: (userContent: string, userSequenceNum: number) => void;
  onDeleteMessage?: (messageId: string) => void;
  disabled?: boolean;
  sessionId?: string;
  onSwitchBranch?: (branchId: number) => void;
}

export function MessageList({
  messages,
  streamingText,
  streamingReasoning,
  streamPhase,
  thinkingElapsed,
  isStreaming,
  onEditMessage,
  onRegenerateMessage,
  onDeleteMessage,
  disabled,
  sessionId,
  onSwitchBranch,
}: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll on new messages or when streaming content changes
  // Use length thresholds to avoid firing on every single character
  const scrollTrigger = `${messages.length}:${(streamingText?.length ?? 0) >> 5}:${(streamingReasoning?.length ?? 0) >> 5}`;
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [scrollTrigger]);

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
      <div className="mx-auto flex w-full max-w-full px-4 md:max-w-[720px] 2xl:max-w-[900px] flex-col gap-5">
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
            onDelete={
              onDeleteMessage
                ? () => onDeleteMessage(msg.message_id)
                : undefined
            }
            disabled={disabled}
            sessionId={sessionId}
            onSwitchBranch={onSwitchBranch}
          />
        ))}

        {/* Streaming assistant message (in progress) */}
        {isStreaming && (streamingText || streamingReasoning) && (
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
              branch_id: 0,
              parent_message_id: null,
              created_at: new Date().toISOString(),
            }}
            isStreamingMsg
            disabled
            streamingReasoning={streamingReasoning}
            isThinkingStreaming={streamPhase === 'thinking'}
            thinkingElapsed={thinkingElapsed}
          />
        )}

        {/* Typing indicator (before any text arrives) */}
        {isStreaming && !streamingText && !streamingReasoning && (
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
