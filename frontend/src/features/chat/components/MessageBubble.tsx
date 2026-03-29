import { useMemo } from 'react';
import type { UIMessage } from '@ai-sdk/react';
import { AssistantMessage } from './AssistantMessage';
import { UserMessage } from './UserMessage';
import { OutputCard } from './OutputCard';
import { extractCodeBlocks } from '../utils/extractCodeBlocks';
import type { ChatOutput } from '../types';

interface MessageBubbleProps {
  message: UIMessage;
  isLastAssistant?: boolean;
  isStreaming?: boolean;
}

function extractText(message: UIMessage): string {
  return message.parts
    .filter((p) => p.type === 'text')
    .map((p) => (p as { type: 'text'; text: string }).text)
    .join('');
}

export function MessageBubble({ message, isLastAssistant, isStreaming }: MessageBubbleProps) {
  const isUser = message.role === 'user';
  const text = extractText(message);

  // Extract code blocks from assistant messages to show as OutputCards
  const codeOutputs = useMemo<ChatOutput[]>(() => {
    if (isUser) return [];
    return extractCodeBlocks(text, message.id);
  }, [isUser, text, message.id]);

  return (
    <div className={['flex gap-3', isUser ? 'justify-end' : 'justify-start'].join(' ')}>
      {!isUser && (
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[11px] font-bold text-primary">
          AI
        </div>
      )}

      <div
        className={[
          'max-w-[75%] rounded-xl px-4 py-2.5 text-sm',
          isUser
            ? 'rounded-br-sm bg-primary text-primary-foreground'
            : 'rounded-bl-sm bg-muted',
        ].join(' ')}
      >
        {isUser ? (
          <UserMessage content={text} />
        ) : (
          <>
            <AssistantMessage
              content={text}
              isStreaming={isLastAssistant && isStreaming}
            />
            {codeOutputs.length > 0 && !isStreaming && (
              <div className="mt-2 space-y-1.5">
                {codeOutputs.map((output) => (
                  <OutputCard key={output.output_id} output={output} />
                ))}
              </div>
            )}
          </>
        )}
      </div>

      {isUser && (
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-muted text-[11px] font-bold text-muted-foreground">
          You
        </div>
      )}
    </div>
  );
}
