import { Brain } from 'lucide-react';

interface ThinkingBlockProps {
  /** Reasoning text content */
  reasoning: string;
  /** Whether reasoning is still streaming */
  isStreaming?: boolean;
  /** Elapsed thinking time in seconds */
  elapsed?: number;
}

export function ThinkingBlock({ reasoning, isStreaming, elapsed }: ThinkingBlockProps) {
  if (!reasoning && !isStreaming) return null;

  const timeLabel = elapsed != null ? `${elapsed.toFixed(1)}s` : '';

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
  return (
    <details className="mb-3 rounded-lg border border-[#3b2d6b] bg-[#1e1633] px-3 py-2.5">
      <summary className="flex cursor-pointer items-center gap-2 list-none text-xs font-medium text-[#a78bfa]">
        <Brain className="h-3.5 w-3.5" />
        <span>Thought for {timeLabel || 'a moment'}</span>
        <svg className="ml-auto h-2.5 w-2.5 transition-transform [[open]>&]:rotate-180" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path d="M19 9l-7 7-7-7" /></svg>
      </summary>
      <div className="mt-2 max-h-[300px] overflow-y-auto border-t border-[#3b2d6b] pt-2">
        <p className="whitespace-pre-wrap font-mono text-xs leading-relaxed text-[#c4b5fd]">
          {reasoning}
        </p>
      </div>
    </details>
  );
}
