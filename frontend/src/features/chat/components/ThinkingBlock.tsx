import { useEffect, useRef, useState } from 'react';
import { AlertTriangle, Brain, ChevronDown, ChevronRight } from 'lucide-react';

interface ThinkingBlockProps {
  reasoning: string;
  isStreaming?: boolean;
  elapsed?: number;
  contentEmpty?: boolean;
}

const LONG_THINKING_THRESHOLD = 10;

export function ThinkingBlock({ reasoning, isStreaming, elapsed, contentEmpty }: ThinkingBlockProps) {
  if (!reasoning && !isStreaming) return null;

  const timeLabel = elapsed != null ? `${elapsed.toFixed(1)}s` : '';
  const isLongThinking = isStreaming && elapsed != null && elapsed > LONG_THINKING_THRESHOLD;

  // Toggle: open while streaming, closed for persisted messages
  const [expanded, setExpanded] = useState(!!isStreaming);
  const contentRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when reasoning streams (like terminal log)
  useEffect(() => {
    if (expanded && contentRef.current) {
      contentRef.current.scrollTop = contentRef.current.scrollHeight;
    }
  }, [reasoning, expanded]);

  // Auto-collapse when streaming ends, auto-expand when streaming starts
  const wasStreamingRef = useRef(isStreaming);
  useEffect(() => {
    if (wasStreamingRef.current && !isStreaming) {
      setExpanded(false);
      wasStreamingRef.current = false;
    } else if (isStreaming && !wasStreamingRef.current) {
      setExpanded(true);
      wasStreamingRef.current = true;
    }
  }, [isStreaming]);

  if (isStreaming) {
    return (
      <div className="mb-3 rounded-lg border border-[#3b2d6b] bg-[#1e1633] p-3">
        {/* Header with toggle */}
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          className="flex w-full items-center gap-2"
        >
          <Brain className="h-3.5 w-3.5 animate-pulse text-[#a78bfa]" />
          <span className="text-xs font-medium text-[#a78bfa]">Thinking...</span>
          {timeLabel && (
            <span className="font-mono text-[11px] text-[#a78bfa]/70">{timeLabel}</span>
          )}
          <span className="ml-auto text-[#a78bfa]/50">
            {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          </span>
        </button>

        {/* Warning */}
        {isLongThinking && (
          <div className="mt-2 flex items-start gap-1.5 rounded border border-yellow-500/20 bg-yellow-500/5 px-2.5 py-1.5">
            <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-yellow-500" />
            <p className="text-[10px] leading-relaxed text-yellow-400/80">
              Model has been thinking for a while without responding.
              You can stop and try a different model or switch to Fast mode.
            </p>
          </div>
        )}

        {/* Expandable reasoning content — scrolls to bottom like terminal */}
        {expanded && reasoning && (
          <div
            ref={contentRef}
            className="mt-2 max-h-[200px] overflow-y-auto border-t border-[#3b2d6b] pt-2"
          >
            <p className="whitespace-pre-wrap font-mono text-xs leading-relaxed text-[#c4b5fd]">
              {reasoning}
            </p>
          </div>
        )}
      </div>
    );
  }

  // Completed thinking — collapsed by default with toggle
  const stuckWarning = contentEmpty && reasoning.length > 200;

  return (
    <div className="mb-3 rounded-lg border border-[#3b2d6b] bg-[#1e1633] px-3 py-2.5">
      {/* Header toggle */}
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2 text-xs font-medium text-[#a78bfa]"
      >
        <Brain className="h-3.5 w-3.5" />
        <span>Thought for {timeLabel || 'a moment'}</span>
        {stuckWarning && (
          <span className="flex items-center gap-1 rounded bg-yellow-500/10 px-1.5 py-0.5 text-[9px] text-yellow-400">
            <AlertTriangle className="h-2.5 w-2.5" />
            No response generated
          </span>
        )}
        <span className="ml-auto text-[#a78bfa]/50">
          {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        </span>
      </button>

      {/* Expanded content */}
      {expanded && (
        <>
          {stuckWarning && (
            <p className="mt-2 rounded border border-yellow-500/20 bg-yellow-500/5 px-2.5 py-1.5 text-[10px] text-yellow-400/80">
              This model produced thinking output but no response. Try Fast mode or a different model.
            </p>
          )}
          <div
            ref={contentRef}
            className="mt-2 max-h-[300px] overflow-y-auto border-t border-[#3b2d6b] pt-2"
          >
            <p className="whitespace-pre-wrap font-mono text-xs leading-relaxed text-[#c4b5fd]">
              {reasoning}
            </p>
          </div>
        </>
      )}
    </div>
  );
}
