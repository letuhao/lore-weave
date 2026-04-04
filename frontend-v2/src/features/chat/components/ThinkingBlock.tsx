import { AlertTriangle, Brain } from 'lucide-react';

interface ThinkingBlockProps {
  /** Reasoning text content */
  reasoning: string;
  /** Whether reasoning is still streaming */
  isStreaming?: boolean;
  /** Elapsed thinking time in seconds */
  elapsed?: number;
  /** Whether the final response content is empty (thinking-only) */
  contentEmpty?: boolean;
}

const LONG_THINKING_THRESHOLD = 10; // seconds

export function ThinkingBlock({ reasoning, isStreaming, elapsed, contentEmpty }: ThinkingBlockProps) {
  if (!reasoning && !isStreaming) return null;

  const timeLabel = elapsed != null ? `${elapsed.toFixed(1)}s` : '';
  const isLongThinking = isStreaming && elapsed != null && elapsed > LONG_THINKING_THRESHOLD;

  if (isStreaming) {
    return (
      <div className="mb-3 rounded-lg border border-[#3b2d6b] bg-[#1e1633] p-3">
        <div className="flex items-center gap-2">
          <Brain className="h-3.5 w-3.5 animate-pulse text-[#a78bfa]" />
          <span className="text-xs font-medium text-[#a78bfa]">Thinking...</span>
          {timeLabel && (
            <span className="ml-auto font-mono text-[11px] text-[#a78bfa]/70">{timeLabel}</span>
          )}
        </div>
        {/* Warning: model may be stuck in thinking loop */}
        {isLongThinking && (
          <div className="mt-2 flex items-start gap-1.5 rounded border border-yellow-500/20 bg-yellow-500/5 px-2.5 py-1.5">
            <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-yellow-500" />
            <p className="text-[10px] leading-relaxed text-yellow-400/80">
              Model has been thinking for a while without responding.
              Some models may get stuck in thinking loops. You can stop and try a different model or switch to Fast mode.
            </p>
          </div>
        )}
        {reasoning && (
          <div className="mt-2 max-h-[200px] overflow-y-auto border-t border-[#3b2d6b] pt-2">
            <p className="whitespace-pre-wrap font-mono text-xs leading-relaxed text-[#c4b5fd]">
              {reasoning}
            </p>
          </div>
        )}
      </div>
    );
  }

  // Completed thinking — collapsible
  // Show warning if thinking completed but content was empty
  const stuckWarning = contentEmpty && reasoning.length > 200;

  return (
    <details className="group mb-3 rounded-lg border border-[#3b2d6b] bg-[#1e1633] px-3 py-2.5">
      <summary className="flex cursor-pointer items-center gap-2 list-none text-xs font-medium text-[#a78bfa]">
        <Brain className="h-3.5 w-3.5" />
        <span>Thought for {timeLabel || 'a moment'}</span>
        {stuckWarning && (
          <span className="flex items-center gap-1 rounded bg-yellow-500/10 px-1.5 py-0.5 text-[9px] text-yellow-400">
            <AlertTriangle className="h-2.5 w-2.5" />
            No response generated
          </span>
        )}
        <svg className="ml-auto h-2.5 w-2.5 transition-transform group-open:rotate-180" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path d="M19 9l-7 7-7-7" /></svg>
      </summary>
      {stuckWarning && (
        <p className="mt-2 rounded border border-yellow-500/20 bg-yellow-500/5 px-2.5 py-1.5 text-[10px] text-yellow-400/80">
          This model produced thinking output but no response. It may not be compatible with thinking mode.
          Try switching to Fast mode or using a different model.
        </p>
      )}
      <div className="mt-2 max-h-[300px] overflow-y-auto border-t border-[#3b2d6b] pt-2">
        <p className="whitespace-pre-wrap font-mono text-xs leading-relaxed text-[#c4b5fd]">
          {reasoning}
        </p>
      </div>
    </details>
  );
}
