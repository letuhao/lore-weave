import { useMemo } from 'react';
import { cn } from '@/lib/utils';
import type { ChatMessage, ChatOutput } from '../types';
import { extractCodeBlocks } from '../utils/extractCodeBlocks';
import { AssistantMessage } from './AssistantMessage';
import { UserMessage } from './UserMessage';
import { OutputCard } from './OutputCard';

interface MessageBubbleProps {
  message: ChatMessage;
  /** Whether this is a streaming placeholder (partial text) */
  isStreamingMsg?: boolean;
  onEdit?: (newContent: string) => void;
  onRegenerate?: () => void;
  disabled?: boolean;
}

export function MessageBubble({
  message,
  isStreamingMsg,
  onEdit,
  onRegenerate,
  disabled,
}: MessageBubbleProps) {
  const isUser = message.role === 'user';
  const text = message.content;

  // Extract code blocks from assistant messages to show as OutputCards
  const codeOutputs = useMemo<ChatOutput[]>(() => {
    if (isUser || isStreamingMsg) return [];
    return extractCodeBlocks(text, message.message_id);
  }, [isUser, isStreamingMsg, text, message.message_id]);

  return (
    <div className={cn('flex', isUser ? 'justify-end' : 'justify-start')}>
      <div
        className={cn(
          'max-w-[85%] px-4 py-3 text-sm',
          isUser
            ? 'rounded-[12px_12px_4px_12px] bg-secondary text-foreground'
            : 'rounded-[12px_12px_12px_4px] border border-border bg-card text-foreground',
        )}
      >
        {isUser ? (
          <UserMessage content={text} onEdit={onEdit} disabled={disabled} />
        ) : (
          <>
            <AssistantMessage
              content={text}
              isStreaming={isStreamingMsg}
              onRegenerate={onRegenerate}
              disabled={disabled}
            />
            {codeOutputs.length > 0 && (
              <div className="mt-2 space-y-1.5">
                {codeOutputs.map((output) => (
                  <OutputCard key={output.output_id} output={output} />
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
