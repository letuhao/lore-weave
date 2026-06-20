import { useState, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Brain,
  Copy,
  MoreHorizontal,
  RefreshCw,
  Send,
  ThumbsDown,
  ThumbsUp,
  Zap,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import rehypeHighlight from 'rehype-highlight';
import { toast } from 'sonner';
import { ThinkingBlock } from './ThinkingBlock';
import { AudioReplayPlayer } from './AudioReplayPlayer';
import { ToolCallIndicator } from './ToolCallIndicator';
import { ProposeEditCard } from './ProposeEditCard';
import { GlossaryDiffCard } from './GlossaryDiffCard';
import { ConfirmCard } from './ConfirmCard';
import { useMessageFeedback } from '../hooks/useMessageFeedback';
import { firePasteToEditor } from '../utils/pasteToEditor';
import type { ToolCallRecord } from '../types';

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
  /** Audio replay (voice pipeline V2) */
  sessionId?: string;
  messageId?: string;
  voiceTtsSentences?: number;
  /** K21-C (D2): memory tool calls made during this turn. */
  toolCalls?: ToolCallRecord[] | null;
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
  sessionId,
  messageId,
  voiceTtsSentences,
  toolCalls,
}: AssistantMessageProps) {
  const { t } = useTranslation('chat');
  const [showMore, setShowMore] = useState(false);
  const moreRef = useRef<HTMLDivElement>(null);
  const feedback = useMessageFeedback(messageId);

  // Regenerate is an implicit negative signal on this turn (the user wasn't
  // satisfied) — post it silently, then run the parent's regenerate.
  function handleRegenerate() {
    if (messageId) void feedback.submit(-1, { reason: 'regenerated' });
    onRegenerate?.();
  }

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
    toast.success(t('message.copied'));
  }

  async function handleCopyMarkdown() {
    await navigator.clipboard.writeText(content);
    toast.success(t('message.copied_markdown'));
    setShowMore(false);
  }

  function handleSendToEditor() {
    firePasteToEditor({ text: content });
    toast.success(t('message.sent_to_editor'));
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

      {/* K21-C (D2): memory tool calls used in this reply. Renders
          nothing when toolCalls is empty/null. ARCH-1 C6: a pending
          propose_edit (frontend write-back tool) renders as an interactive
          Apply/Dismiss card instead of a passive chip. */}
      {toolCalls && toolCalls.length > 0 && (() => {
        // H15: route a pending (suspended) frontend tool to its renderer BY NAME.
        // propose_edit → prose card; glossary_propose_entity_edit → diff card.
        const FRONTEND_TOOLS = ['propose_edit', 'glossary_propose_entity_edit', 'glossary_confirm_action'];
        const isPendingFrontend = (tc: ToolCallRecord) =>
          tc.pending === true && FRONTEND_TOOLS.includes(tc.tool);
        const proposals = toolCalls.filter(isPendingFrontend);
        const rest = toolCalls.filter((tc) => !isPendingFrontend(tc));
        return (
          <>
            {rest.length > 0 && <ToolCallIndicator toolCalls={rest} />}
            {proposals.map((tc) => {
              const key = tc.toolCallId ?? tc.tool;
              if (tc.tool === 'glossary_propose_entity_edit') return <GlossaryDiffCard key={key} record={tc} />;
              if (tc.tool === 'glossary_confirm_action') return <ConfirmCard key={key} record={tc} />;
              return <ProposeEditCard key={key} record={tc} />;
            })}
          </>
        );
      })()}

      {/* Audio replay (voice pipeline V2) */}
      {!isStreaming && sessionId && messageId && voiceTtsSentences && voiceTtsSentences > 0 && (
        <AudioReplayPlayer sessionId={sessionId} messageId={messageId} />
      )}

      {/* Token footer + action buttons */}
      {!isStreaming && (
        <div className="mt-1.5 flex flex-wrap items-center justify-between gap-y-1 opacity-0 transition-opacity group-hover:opacity-100 max-md:opacity-100">
          {/* Token counts + timing */}
          {hasMetrics && (
            <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 font-mono text-[10px] text-muted-foreground">
              {hasReasoning ? (
                <span className="flex items-center gap-0.5 text-[#a78bfa]">
                  <Brain className="h-2.5 w-2.5" />
                  {t('input.think')}
                </span>
              ) : (
                <span className="flex items-center gap-0.5 text-accent">
                  <Zap className="h-2.5 w-2.5" />
                  {t('input.fast')}
                </span>
              )}
              {inputTokens != null && <span>&uarr;{inputTokens.toLocaleString()}</span>}
              {outputTokens != null && <span>&darr;{outputTokens.toLocaleString()}</span>}
              {responseTimeMs != null && (
                <span>&middot; {(responseTimeMs / 1000).toFixed(1)}s</span>
              )}
              {timeToFirstTokenMs != null && (
                <span title={t('message.ttft')}>TTFT {timeToFirstTokenMs}ms</span>
              )}
            </div>
          )}

          {/* Action buttons */}
          {!disabled && (
            <div className="flex items-center gap-1">
              {messageId && (
                <>
                  <button
                    type="button"
                    onClick={() => void feedback.submit(1)}
                    disabled={feedback.submitting}
                    aria-pressed={feedback.rating === 1}
                    title={t('message.feedback_up')}
                    className={`rounded p-1 transition-colors hover:bg-secondary ${
                      feedback.rating === 1
                        ? 'text-emerald-400'
                        : 'text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    <ThumbsUp className="h-3.5 w-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => void feedback.submit(-1)}
                    disabled={feedback.submitting}
                    aria-pressed={feedback.rating === -1}
                    title={t('message.feedback_down')}
                    className={`rounded p-1 transition-colors hover:bg-secondary ${
                      feedback.rating === -1
                        ? 'text-red-400'
                        : 'text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    <ThumbsDown className="h-3.5 w-3.5" />
                  </button>
                </>
              )}
              <button
                type="button"
                onClick={handleCopy}
                title={t('message.copy')}
                className="rounded p-1 text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
              >
                <Copy className="h-3.5 w-3.5" />
              </button>
              {onRegenerate && (
                <button
                  type="button"
                  onClick={handleRegenerate}
                  title={t('message.regenerate')}
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
                  title={t('message.more_actions')}
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
                      {t('message.copy_markdown')}
                    </button>
                    <button
                      type="button"
                      onClick={handleSendToEditor}
                      className="flex w-full items-center gap-2 px-3 py-1.5 text-xs text-foreground hover:bg-secondary transition-colors"
                    >
                      <Send className="h-3 w-3" />
                      {t('message.send_to_editor')}
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
