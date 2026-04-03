import { useMemo } from 'react';
import { BookOpen, FileText } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ChatMessage, ChatOutput } from '../types';
import { extractCodeBlocks } from '../utils/extractCodeBlocks';
import { hasContext, extractUserMessage, extractContextLabels } from '../context/types';
import { AssistantMessage } from './AssistantMessage';
import { BranchNavigator } from './BranchNavigator';
import { UserMessage } from './UserMessage';
import { OutputCard } from './OutputCard';

interface MessageBubbleProps {
  message: ChatMessage;
  /** Whether this is a streaming placeholder (partial text) */
  isStreamingMsg?: boolean;
  onEdit?: (newContent: string) => void;
  onRegenerate?: () => void;
  disabled?: boolean;
  /** Streaming reasoning text (only for active streaming message) */
  streamingReasoning?: string;
  /** Whether reasoning is actively streaming */
  isThinkingStreaming?: boolean;
  /** Elapsed thinking time */
  thinkingElapsed?: number;
  /** Session ID for branch navigation */
  sessionId?: string;
  /** Called when user switches branch */
  onSwitchBranch?: (branchId: number) => void;
}

const CONTEXT_PILL_ICON: Record<string, React.ReactNode> = {
  Book: <BookOpen className="h-[10px] w-[10px]" />,
  Chapter: <FileText className="h-[10px] w-[10px]" />,
  Glossary: (
    <svg className="h-[10px] w-[10px]" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
      <path d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 01-1.806-1.741L3.842 10.1a2 2 0 011.075-2.029l1.29-.645a6 6 0 013.86-.517l.318.158a6 6 0 003.86.517l2.387-.477a2 2 0 012.368 2.367l-.402 2.814a2 2 0 01-.77 1.34z" />
    </svg>
  ),
};

const CONTEXT_PILL_STYLES: Record<string, string> = {
  Book: 'bg-primary/10 border-primary/20 text-primary',
  Chapter: 'bg-accent/10 border-accent/20 text-accent',
  Glossary: 'bg-blue-500/8 border-blue-500/15 text-blue-400',
};

export function MessageBubble({
  message,
  isStreamingMsg,
  onEdit,
  onRegenerate,
  disabled,
  streamingReasoning,
  isThinkingStreaming,
  thinkingElapsed,
  sessionId,
  onSwitchBranch,
}: MessageBubbleProps) {
  const isUser = message.role === 'user';
  const rawContent = message.content;

  // Separate context from user message
  const messageHasContext = isUser && hasContext(rawContent);
  const displayText = messageHasContext ? extractUserMessage(rawContent) : rawContent;
  const contextLabels = useMemo(
    () => (messageHasContext ? extractContextLabels(rawContent) : []),
    [messageHasContext, rawContent],
  );

  // Extract code blocks from assistant messages to show as OutputCards
  const codeOutputs = useMemo<ChatOutput[]>(() => {
    if (isUser || isStreamingMsg) return [];
    return extractCodeBlocks(rawContent, message.message_id);
  }, [isUser, isStreamingMsg, rawContent, message.message_id]);

  return (
    <div className={cn('flex', isUser ? 'justify-end' : 'justify-start')}>
      <div className="max-w-[85%]">
        {/* Context pills above user message */}
        {messageHasContext && contextLabels.length > 0 && (
          <div className="mb-1 flex flex-wrap justify-end gap-1">
            {contextLabels.map((label, i) => {
              // Parse "[Type: Name]" format
              const match = label.match(/\[(\w+): (.+)\]/);
              const type = match?.[1] ?? 'Book';
              const name = match?.[2] ?? label;
              return (
                <span
                  key={i}
                  className={cn(
                    'inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] font-medium',
                    CONTEXT_PILL_STYLES[type] ?? CONTEXT_PILL_STYLES.Book,
                  )}
                >
                  {CONTEXT_PILL_ICON[type]}
                  {name.length > 20 ? name.slice(0, 20) + '\u2026' : name} attached
                </span>
              );
            })}
          </div>
        )}

        <div
          className={cn(
            'px-4 py-3 text-sm',
            isUser
              ? 'rounded-[12px_12px_4px_12px] bg-secondary text-foreground'
              : 'rounded-[12px_12px_12px_4px] border border-border bg-card text-foreground',
          )}
        >
          {isUser ? (
            <>
              <UserMessage content={displayText} onEdit={onEdit} disabled={disabled} />
              {/* Branch navigator — shown on edited messages (have parent_message_id) */}
              {message.parent_message_id && sessionId && onSwitchBranch && (
                <div className="mt-1.5 flex justify-end">
                  <BranchNavigator
                    sessionId={sessionId}
                    forkSequenceNum={message.sequence_num - 1}
                    activeBranchId={message.branch_id ?? 0}
                    onSwitchBranch={onSwitchBranch}
                  />
                </div>
              )}
            </>
          ) : (
            <>
              <AssistantMessage
                content={displayText}
                isStreaming={isStreamingMsg}
                onRegenerate={onRegenerate}
                disabled={disabled}
                reasoning={
                  isStreamingMsg
                    ? streamingReasoning
                    : (message.content_parts as { reasoning?: string } | null)?.reasoning
                }
                isThinkingStreaming={isStreamingMsg ? isThinkingStreaming : false}
                thinkingElapsed={isStreamingMsg ? thinkingElapsed : undefined}
                inputTokens={message.input_tokens}
                outputTokens={message.output_tokens}
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
    </div>
  );
}
