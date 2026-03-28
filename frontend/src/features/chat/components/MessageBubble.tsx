import type { UIMessage } from '@ai-sdk/react';
import { AssistantMessage } from './AssistantMessage';
import { UserMessage } from './UserMessage';

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
          <AssistantMessage
            content={text}
            isStreaming={isLastAssistant && isStreaming}
          />
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
