import { Brain, Copy, RefreshCw, Zap } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import rehypeHighlight from 'rehype-highlight';
import { toast } from 'sonner';
import { ThinkingBlock } from './ThinkingBlock';

interface AssistantMessageProps {
  content: string;
  isStreaming?: boolean;
  onRegenerate?: () => void;
  disabled?: boolean;
  /** Reasoning text (from content_parts or streaming) */
  reasoning?: string;
  /** Whether reasoning is actively streaming */
  isThinkingStreaming?: boolean;
  /** Elapsed thinking time in seconds */
  thinkingElapsed?: number;
  /** Token counts (from persisted message) */
  inputTokens?: number | null;
  outputTokens?: number | null;
}

export function AssistantMessage({
  content,
  isStreaming,
  onRegenerate,
  disabled,
  reasoning,
  isThinkingStreaming,
  thinkingElapsed,
  inputTokens,
  outputTokens,
}: AssistantMessageProps) {
  async function handleCopy() {
    await navigator.clipboard.writeText(content);
    toast.success('Copied to clipboard');
  }

  const hasReasoning = !!reasoning || isThinkingStreaming;
  const hasTokens = inputTokens != null || outputTokens != null;

  return (
    <div className="group relative">
      {/* Thinking block */}
      {hasReasoning && (
        <ThinkingBlock
          reasoning={reasoning ?? ''}
          isStreaming={isThinkingStreaming}
          elapsed={thinkingElapsed}
        />
      )}

      {/* Main content */}
      <div className="prose prose-sm prose-invert max-w-none break-words [&_strong]:text-amber-400 [&_li]:text-foreground/90 [&_p]:text-foreground/90">
        <ReactMarkdown rehypePlugins={[rehypeHighlight]}>{content}</ReactMarkdown>
        {isStreaming && (
          <span className="inline-block h-4 w-1.5 animate-pulse rounded-sm bg-accent opacity-80" />
        )}
      </div>

      {/* Token footer + action buttons */}
      {!isStreaming && (
        <div className="mt-1.5 flex items-center justify-between opacity-0 transition-opacity group-hover:opacity-100">
          {/* Token counts */}
          {hasTokens && (
            <div className="flex items-center gap-2 font-mono text-[10px] text-muted-foreground">
              {hasReasoning && (
                <span className="flex items-center gap-0.5 text-[#a78bfa]">
                  <Brain className="h-2.5 w-2.5" />
                  {reasoning ? reasoning.length : 0}
                </span>
              )}
              {!hasReasoning && (
                <span className="flex items-center gap-0.5 text-accent">
                  <Zap className="h-2.5 w-2.5" />
                  Fast
                </span>
              )}
              {inputTokens != null && <span>&uarr; {inputTokens.toLocaleString()}</span>}
              {outputTokens != null && <span>&darr; {outputTokens.toLocaleString()}</span>}
            </div>
          )}

          {/* Action buttons */}
          {!disabled && (
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={handleCopy}
                title="Copy"
                className="rounded p-1 text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
              >
                <Copy className="h-3.5 w-3.5" />
              </button>
              {onRegenerate && (
                <button
                  type="button"
                  onClick={onRegenerate}
                  title="Regenerate"
                  className="rounded p-1 text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
