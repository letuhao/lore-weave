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
import { ConfirmActionCard, descriptorDomain } from './ConfirmActionCard';
import { BatchConfirmCard, type BatchChild } from './BatchConfirmCard';
import { RecordDiffCard } from './RecordDiffCard';
import { ToolApprovalCard, isToolApprovalRecord } from './ToolApprovalCard';
import { TranslationReviewCard, isTranslationProposeCall, summarizeTranslationReview } from './TranslationReviewCard';
import { SkillProposalCard, skillProposal, type SkillProposal } from './SkillProposalCard';
import { ActivityStrip } from './ActivityStrip';
import { useMessageFeedback } from '../hooks/useMessageFeedback';
import { useActivityUndo } from '../hooks/useActivityUndo';
import { firePasteToEditor } from '../utils/pasteToEditor';
import type { ActivityEvent, ToolCallRecord } from '../types';

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
  /** MCP fan-out (C-ACTIVITY): Tier-A auto-applied ops streamed this turn. */
  activities?: ActivityEvent[] | null;
  /** DBT-CHAT-PERSIST — how the turn ended. 'interrupted' (user stopped, or a
   *  frontend-tool card was abandoned/expired) or 'error' (threw mid-stream)
   *  render an "incomplete" badge so a partial reply is clearly marked instead
   *  of looking like a finished answer. null/'stop'/undefined → no badge. */
  finishReason?: string | null;
  /** N2 (dogfood 2026-07-18 F4) — host-aware "insert this reply into the chapter". When a parent
   * supplies it (the studio co-writer, via useAcceptIntoEditor) it wins; otherwise the button falls
   * back to the paste-to-editor event, which the studio EditorPanel + the legacy editor page both
   * listen for. AssistantMessage never touches useStudioHost itself — it renders in /chat too, which
   * has no StudioHostProvider — so the host-aware handler is INJECTED, never imported here. */
  onInsert?: (text: string) => void;
}

// ── Auto-rendered confirm cards (model-independent human gate) ────────────────
// A class-C glossary tool (glossary_propose_new_kind/_attribute, glossary_book_delete,
// adopt/sync/revert/status/merge/restore, deep_research) MINTS a confirm_token in its
// RESULT but performs no write — the human gate is the confirm card. A capable model
// then calls the frontend glossary_confirm_action tool to render it, but weaker local
// models routinely skip that call, leaving the user with no way to approve. So we ALSO
// auto-render a confirm card directly from a completed propose result that carries a
// live confirm_token (independent of whether the model called the frontend tool). The
// reused card's resume() safely no-ops without a runId; Confirm still POSTs to
// /v1/<domain>/actions/confirm (the only write path, single-use).
interface ProposeConfirm { confirm_token: string; descriptor?: string; title?: string }

/** The action token's claims are its base64url segment-0 (a 2-part token:
 * claims.hmac, not a JWT header.payload). Return false once past `exp` so stale
 * proposals on REPLAY don't render dead approve cards. Unparseable → treat as live
 * (the confirm/preview call re-validates authoritatively). */
function actionTokenLive(token: string): boolean {
  try {
    const seg = token.split('.')[0];
    const claims = JSON.parse(atob(seg.replace(/-/g, '+').replace(/_/g, '/'))) as { exp?: number };
    if (typeof claims.exp === 'number') return claims.exp * 1000 > Date.now();
  } catch { /* fall through — confirm re-validates */ }
  return true;
}

/** Extract a confirm payload from a COMPLETED propose tool result. Handles the
 * {confirm_token,...}, {result:{confirm_token,...}} and JSON-string shapes. */
function proposeConfirm(tc: ToolCallRecord): ProposeConfirm | null {
  if (tc.pending) return null;
  let r: unknown = tc.result;
  if (typeof r === 'string') { try { r = JSON.parse(r); } catch { return null; } }
  if (!r || typeof r !== 'object') return null;
  const o = r as Record<string, unknown>;
  const p = (typeof o.confirm_token === 'string' ? o
    : (o.result && typeof o.result === 'object' ? o.result as Record<string, unknown> : null));
  if (!p || typeof p.confirm_token !== 'string' || !p.confirm_token) return null;
  // Glossary propose tools return `title`; KG tools return `summary` — accept either
  // so the auto-card has a label without waiting on the (best-effort) preview fetch.
  const label = typeof p.title === 'string' ? p.title
    : typeof p.summary === 'string' ? p.summary : undefined;
  return {
    confirm_token: p.confirm_token,
    descriptor: typeof p.descriptor === 'string' ? p.descriptor : undefined,
    title: label,
  };
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
  activities,
  onInsert,
  finishReason,
}: AssistantMessageProps) {
  const { t } = useTranslation('chat');
  const [showMore, setShowMore] = useState(false);
  const moreRef = useRef<HTMLDivElement>(null);
  const feedback = useMessageFeedback(messageId);
  const undoActivity = useActivityUndo();

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

  // N2 — converge the (previously buried, overflow-only) "send to editor" into one first-class
  // "Insert" action. Host-aware handler wins when the parent injects it (studio); else fall back to
  // the paste-to-editor event that the studio EditorPanel + the legacy editor page both consume.
  function handleInsert() {
    if (onInsert) onInsert(content);
    else firePasteToEditor({ text: content });
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

      {/* DBT-CHAT-PERSIST — incomplete-turn badge. A turn that ended by user
          interrupt or a mid-stream error (incl. an abandoned/expired frontend-tool
          card) is persisted with its partial text and shown with this marker,
          rather than vanishing on reload. */}
      {!isStreaming && (finishReason === 'interrupted' || finishReason === 'error') && (
        <div
          data-testid="message-incomplete-badge"
          className={`mt-1 inline-flex items-center gap-1.5 rounded px-1.5 py-0.5 text-[11px] ${
            finishReason === 'error'
              ? 'bg-red-500/10 text-red-400/90'
              : 'bg-amber-500/10 text-amber-400/90'
          }`}
        >
          <span
            className={`h-1.5 w-1.5 rounded-full ${
              finishReason === 'error' ? 'bg-red-400/80' : 'bg-amber-400/80'
            }`}
          />
          {finishReason === 'error'
            ? t('message.incomplete_error', { defaultValue: 'Error — response incomplete' })
            : t('message.incomplete_interrupted', {
                defaultValue: 'Interrupted — response incomplete',
              })}
        </div>
      )}

      {/* K21-C (D2): memory tool calls used in this reply. Renders
          nothing when toolCalls is empty/null. ARCH-1 C6: a pending
          propose_edit (frontend write-back tool) renders as an interactive
          Apply/Dismiss card instead of a passive chip. */}
      {toolCalls && toolCalls.length > 0 && (() => {
        // H15: route a pending (suspended) frontend tool to its renderer BY NAME.
        //   propose_edit                  → prose card
        //   glossary_propose_entity_edit  → glossary diff card (legacy)
        //   glossary_confirm_action       → glossary confirm card (legacy)
        //   confirm_action               → GENERIC confirm card (C-CONFIRM, incl. batch)
        //   propose_record_edit          → GENERIC record-diff card (C-PROPOSE)
        // ui_* nav tools are NOT rendered here — useUiToolExecutor resolves them
        // headlessly (no human gate), so they never reach this surface.
        const FRONTEND_TOOLS = [
          'propose_edit',
          'glossary_propose_entity_edit',
          'glossary_confirm_action',
          'confirm_action',
          'propose_record_edit',
        ];
        const isPendingFrontend = (tc: ToolCallRecord) =>
          tc.pending === true && FRONTEND_TOOLS.includes(tc.tool);
        // RAID C2 — a pending Tier-A `tool_approval` suspension (args.kind
        // marker; the record's `tool` is the SERVER tool name, e.g.
        // book_create, so it can't route by name). Approve once / Always allow
        // / Deny resume the run via the standard tool-results endpoint.
        const approvals = toolCalls.filter(isToolApprovalRecord);
        const proposals = toolCalls.filter(
          (tc) => isPendingFrontend(tc) && !isToolApprovalRecord(tc),
        );
        // S4: completed class-W translation/alias proposals render as a review card
        // (visible drafts), not a passive chip — but ONLY when the record carries
        // something renderable. A sparse record (e.g. replayed {tool, ok} with no
        // args/result) has no summary, so it stays a chip rather than vanishing from
        // both surfaces.
        const isRenderableTranslation = (tc: ToolCallRecord) =>
          isTranslationProposeCall(tc) && summarizeTranslationReview(tc) !== null;
        const translationCards = toolCalls.filter(isRenderableTranslation);
        // D-REG-SKILLPROPOSAL-CARD: a completed registry_propose_skill/update result
        // renders as an approve/reject card (spec §12b), not a passive chip.
        const skillProposals = toolCalls
          .map(skillProposal)
          .filter((p): p is SkillProposal => p !== null);
        const rest = toolCalls.filter(
          (tc) => !isPendingFrontend(tc) && !isRenderableTranslation(tc) && !isToolApprovalRecord(tc) && !skillProposal(tc),
        );
        // Model-independent human gate: auto-render a confirm card for any completed
        // propose result that minted a LIVE confirm_token, unless an explicit (pending)
        // confirm card already handles that token (avoid double cards). Deduped by token.
        const explicitTokens = new Set(
          toolCalls
            .filter((tc) => tc.pending && (tc.tool === 'glossary_confirm_action' || tc.tool === 'confirm_action'))
            .map((tc) => (tc.args as { confirm_token?: string } | undefined)?.confirm_token)
            .filter((x): x is string => !!x),
        );
        const seenTokens = new Set<string>();
        const autoConfirms: ProposeConfirm[] = [];
        for (const tc of toolCalls) {
          const p = proposeConfirm(tc);
          if (!p || explicitTokens.has(p.confirm_token) || seenTokens.has(p.confirm_token)) continue;
          if (!actionTokenLive(p.confirm_token)) continue;
          seenTokens.add(p.confirm_token);
          autoConfirms.push(p);
        }
        // #27/#29/#30 COALESCE — when a turn produced MORE THAN ONE live confirm token
        // (a weak model looped single-propose tools), fold them ALL into ONE batch card
        // ("Confirm all") instead of N cards that orphan each other. Gathers the explicit
        // pending confirm cards + the auto-rendered ones; non-confirm frontend tools
        // (propose_edit, translation review, record-diff) still render individually.
        const confirmProposals = proposals.filter(
          (tc) =>
            (tc.tool === 'glossary_confirm_action' || tc.tool === 'confirm_action') &&
            !!(tc.args as { confirm_token?: string } | undefined)?.confirm_token,
        );
        const batchChildren: BatchChild[] = [];
        const batchTokens = new Set<string>();
        const addChild = (token: string | undefined, descriptor?: string, ttl?: string, argDomain?: string) => {
          if (!token || batchTokens.has(token)) return;
          batchTokens.add(token);
          batchChildren.push({ token, domain: argDomain ?? descriptorDomain(descriptor) ?? 'glossary', descriptor, title: ttl });
        };
        for (const tc of confirmProposals) {
          const a = (tc.args ?? {}) as { confirm_token?: string; descriptor?: string; title?: string; domain?: string };
          addChild(a.confirm_token, a.descriptor, a.title, a.domain);
        }
        for (const p of autoConfirms) addChild(p.confirm_token, p.descriptor, p.title);
        const coalesce = batchChildren.length > 1;
        // The explicit confirm that suspended the run (≤1 per turn) — resume it ONCE after
        // the whole batch commits so the agent learns the outcome.
        const batchResume = confirmProposals.find((tc) => tc.runId && tc.toolCallId);
        const proposalsToRender = coalesce ? proposals.filter((tc) => !confirmProposals.includes(tc)) : proposals;
        const autoToRender = coalesce ? [] : autoConfirms;
        return (
          <>
            {rest.length > 0 && <ToolCallIndicator toolCalls={rest} />}
            {/* RAID C2 — Tier-A approval cards (Approve once / Always / Deny). */}
            {approvals.map((tc) => (
              <ToolApprovalCard key={tc.toolCallId ?? `${tc.tool}-approval`} record={tc} />
            ))}
            {translationCards.map((tc) => (
              <TranslationReviewCard key={tc.toolCallId ?? `${tc.tool}-${tc.iteration ?? 0}`} record={tc} />
            ))}
            {/* D-REG-SKILLPROPOSAL-CARD — agent skill proposals (approve/reject). */}
            {skillProposals.map((p) => (
              <SkillProposalCard key={p.proposalId} proposal={p} />
            ))}
            {coalesce && (
              <BatchConfirmCard
                children={batchChildren}
                resume={
                  batchResume?.runId && batchResume.toolCallId
                    ? { runId: batchResume.runId, toolCallId: batchResume.toolCallId }
                    : undefined
                }
              />
            )}
            {proposalsToRender.map((tc) => {
              const key = tc.toolCallId ?? tc.tool;
              if (tc.tool === 'glossary_propose_entity_edit') return <GlossaryDiffCard key={key} record={tc} />;
              if (tc.tool === 'glossary_confirm_action') {
                // Route BY DESCRIPTOR, not just tool name: on a book-scoped chat the
                // model is offered both glossary_confirm_action (glossary-only) and
                // the generic confirm_action, and may pick the glossary tool for a
                // NON-glossary action (e.g. book.publish). A dotted generic-domain
                // descriptor → the generic card (commits to /v1/<domain>/actions/*);
                // glossary's own non-dotted descriptors → the legacy glossary card.
                const desc = (tc.args as { descriptor?: string } | undefined)?.descriptor;
                if (descriptorDomain(desc)) return <ConfirmActionCard key={key} record={tc} />;
                return <ConfirmCard key={key} record={tc} />;
              }
              if (tc.tool === 'confirm_action') return <ConfirmActionCard key={key} record={tc} />;
              if (tc.tool === 'propose_record_edit') return <RecordDiffCard key={key} record={tc} />;
              return <ProposeEditCard key={key} record={tc} />;
            })}
            {/* Auto-rendered confirm cards (model called the propose tool but not the
                frontend confirm tool). Synthetic record: no runId → resume no-ops;
                Confirm POSTs to the real /actions/confirm endpoint. Routed by
                descriptor domain (dotted generic → ConfirmActionCard, glossary's
                non-dotted → ConfirmCard). */}
            {autoToRender.map((p) => {
              const synthetic: ToolCallRecord = {
                tool: 'glossary_confirm_action',
                ok: true,
                args: { confirm_token: p.confirm_token, descriptor: p.descriptor, title: p.title },
              };
              const key = `auto-${p.confirm_token.slice(0, 20)}`;
              return descriptorDomain(p.descriptor)
                ? <ConfirmActionCard key={key} record={synthetic} />
                : <ConfirmCard key={key} record={synthetic} />;
            })}
          </>
        );
      })()}

      {/* MCP fan-out (C-ACTIVITY): Tier-A auto-applied ops + Undo. Renders
          nothing when the turn auto-applied nothing. */}
      {activities && activities.length > 0 && (
        <ActivityStrip activities={activities} onUndo={undoActivity} disabled={disabled} />
      )}

      {/* Audio replay (voice pipeline V2) */}
      {!isStreaming && sessionId && messageId && voiceTtsSentences && voiceTtsSentences > 0 && (
        <AudioReplayPlayer sessionId={sessionId} messageId={messageId} />
      )}

      {/* Token footer + action buttons. W2 (Windsurf pattern): the per-message
          token one-liner (↑in ↓out · timing) is ALWAYS visible — a muted
          text-[10px] line, no layout shift; only the action buttons stay
          hover-revealed. */}
      {!isStreaming && (
        <div className="mt-1.5 flex flex-wrap items-center justify-between gap-y-1">
          {/* Token counts + timing */}
          {hasMetrics && (
            <div data-testid="message-token-footer" className="flex flex-wrap items-center gap-x-2 gap-y-0.5 font-mono text-[10px] text-muted-foreground">
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

          {/* Action buttons — hover-revealed (the metrics line above stays). */}
          {!disabled && (
            <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100 max-md:opacity-100">
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
              {/* N2 (F4) — first-class "Insert into chapter": the Cursor-"Apply" parity a newcomer
                  expects, promoted out of the buried overflow. Shown on a completed reply with text. */}
              {!isStreaming && content.trim() && (
                <button
                  type="button"
                  onClick={handleInsert}
                  title={t('message.insert_into_chapter', { defaultValue: 'Insert into chapter' })}
                  className="rounded p-1 text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
                >
                  <Send className="h-3.5 w-3.5" />
                </button>
              )}
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
