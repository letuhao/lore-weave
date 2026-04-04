import { useState, useRef, useEffect } from 'react';
import { Brain, Copy, MoreHorizontal, RefreshCw, Send, Zap } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import rehypeHighlight from 'rehype-highlight';
import { toast } from 'sonner';
import { ThinkingBlock } from './ThinkingBlock';
import { firePasteToEditor } from '../utils/pasteToEditor';

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
  /** Timing metrics from content_parts */
  responseTimeMs?: number | null;
  timeToFirstTokenMs?: number | null;
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
  responseTimeMs,
  timeToFirstTokenMs,
}: AssistantMessageProps) {
  const [showMore, setShowMore] = useState(false);
  const moreRef = useRef<HTMLDivElement>(null);

  // Close dropdown on outside click
  useEffect(() => {
    if (!showMore) return;
    function handleClick(e: MouseEvent) {
      if (moreRef.current && !moreRef.current.contains(e.target as Node)) setShowMore(false);
    }
    window.addEventListener('mousedown', handleClick);
    return () => window.removeEventListener('mousedown', handleClick);
  }, [showMore]);

  async function handleCopy() {
    await navigator.clipboard.writeText(content);
    toast.success('Copied to clipboard');
  }

  async function handleCopyMarkdown() {
    await navigator.clipboard.writeText(content);
    toast.success('Copied as markdown');
    setShowMore(false);
  }

  function handleSendToEditor() {
    firePasteToEditor({ text: content });
    toast.success('Sent to editor — open a chapter to paste');
    setShowMore(false);
  }

  const hasReasoning = !!reasoning || isThinkingStreaming;
  const hasTokens = inputTokens != null || outputTokens != null;
  const hasMetrics = hasTokens || responseTimeMs != null;

  return (
    <div className="group relative">
      {/* Thinking block */}
      {hasReasoning && (
        <ThinkingBlock
          reasoning={reasoning ?? ''}
          isStreaming={isThinkingStreaming}
          elapsed={thinkingElapsed}
          contentEmpty={!isStreaming && !content.trim()}
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
          {/* Token counts + timing */}
          {hasMetrics && (
            <div className="flex items-center gap-2 font-mono text-[10px] text-muted-foreground">
              {hasReasoning ? (
                <span className="flex items-center gap-0.5 text-[#a78bfa]">
                  <Brain className="h-2.5 w-2.5" />
                  Think
                </span>
              ) : (
                <span className="flex items-center gap-0.5 text-accent">
                  <Zap className="h-2.5 w-2.5" />
                  Fast
                </span>
              )}
              {inputTokens != null && <span>&uarr;{inputTokens.toLocaleString()}</span>}
              {outputTokens != null && <span>&darr;{outputTokens.toLocaleString()}</span>}
              {responseTimeMs != null && (
                <span>&middot; {(responseTimeMs / 1000).toFixed(1)}s</span>
              )}
              {timeToFirstTokenMs != null && (
                <span title="Time to first token">TTFT {timeToFirstTokenMs}ms</span>
              )}
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
              {/* More actions dropdown */}
              <div ref={moreRef} className="relative">
                <button
                  type="button"
                  onClick={() => setShowMore(!showMore)}
                  title="More actions"
                  className="rounded p-1 text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
                >
                  <MoreHorizontal className="h-3.5 w-3.5" />
                </button>
                {showMore && (
                  <div className="absolute right-0 bottom-full mb-1 z-10 min-w-[140px] rounded-md border border-border bg-card py-1 shadow-lg">
                    <button
                      type="button"
                      onClick={handleCopyMarkdown}
                      className="flex w-full items-center gap-2 px-3 py-1.5 text-xs text-foreground hover:bg-secondary transition-colors"
                    >
                      <Copy className="h-3 w-3" />
                      Copy Markdown
                    </button>
                    <button
                      type="button"
                      onClick={handleSendToEditor}
                      className="flex w-full items-center gap-2 px-3 py-1.5 text-xs text-foreground hover:bg-secondary transition-colors"
                    >
                      <Send className="h-3 w-3" />
                      Send to Editor
                    </button>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
