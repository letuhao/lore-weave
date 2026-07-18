// WS-1.10 — the /assistant route. Provisions the diary + assistant project on open (idempotent),
// then lays out the reused chat surface (left) beside the home strip (right). The chat is the SAME
// features/chat surface (spec 02 D12 — "not a new surface"), bound to the diary book + stamped
// session_kind='assistant' so recall + capture gate on it.
import { Chat } from '@/features/chat/Chat';
import { useIsMobile } from '@/hooks/useIsMobile';
import { cn } from '@/lib/utils';
import { AssistantProvider, useAssistant } from '../context/AssistantContext';
import { useAssistantFirstRun } from '../hooks/useAssistantFirstRun';
import { AssistantHomeStrip } from './AssistantHomeStrip';
import { MobileAssistantDock } from './mobile/MobileAssistantDock';
import { MobileAssistantFirstRun } from './mobile/MobileAssistantFirstRun';
import { MobileAssistantHeader } from './mobile/MobileAssistantHeader';

function AssistantPageInner() {
  const { loading, error, provisioned, bookId, projectId, reprovision } = useAssistant();
  const isMobile = useIsMobile();
  const firstRun = useAssistantFirstRun();

  // Only show the full-surface spinner during the INITIAL provisioning (before we have a bookId).
  // A later background re-provision must NOT blank the mounted <Chat> (audit HIGH #1 defense — the
  // primary fix is that a token refresh no longer re-provisions at all).
  if (loading && !bookId) {
    return (
      <div className="flex h-full items-center justify-center" data-testid="assistant-loading">
        <p className="text-sm text-muted-foreground">Setting up your assistant…</p>
      </div>
    );
  }

  // Gate on projectId too (audit LOW #4): `provisioned` already implies the assistant project exists,
  // but if it were ever null the consent toggle would render permanently dead — surface an error
  // (with Retry) instead of a silently-disabled control.
  if (error || !provisioned || !bookId || !projectId) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3" data-testid="assistant-error">
        <p className="max-w-sm text-center text-sm text-muted-foreground">
          {error ?? 'The assistant is not ready yet.'}
        </p>
        <button
          type="button"
          onClick={reprovision}
          className="rounded-md border border-border px-4 py-2 text-sm font-medium"
        >
          Retry
        </button>
      </div>
    );
  }

  // FR — on mobile, hold the layout while the first-run flag is still loading. Rendering the <Chat>
  // (which opens the SSE stream) only to replace it with the first-run screen a tick later would
  // mount-then-unmount a stateful component and churn the stream — the exact conditional-unmount the
  // CLAUDE.md FE rules forbid. Desktop has no first-run, so it never waits.
  if (isMobile && firstRun.isLoading) {
    return (
      <div className="flex h-full items-center justify-center" data-testid="assistant-first-run-loading">
        <p className="text-sm text-muted-foreground">Opening your journal…</p>
      </div>
    );
  }

  // FR (draft frame 13) — the mobile journal first-run: shown ONCE (server-gated) after provisioning
  // is ready (it needs projectId for the consent toggle), before the chat. Desktop keeps the strip
  // (which already surfaces consent/tz), so first-run is a mobile affordance.
  if (isMobile && firstRun.shouldShow) {
    return <MobileAssistantFirstRun onDone={firstRun.markDone} />;
  }

  // The <Chat> is the STABLE first child in every layout — swapping the second child (mobile
  // dock vs desktop rail) by viewport never remounts it, so the SSE stream / voice / unsaved
  // input survive a rotate (MB1). Mobile stacks vertically (chat fills, dock at the bottom);
  // desktop keeps the right rail.
  return (
    <div
      className={cn('flex h-full min-h-0', isMobile ? 'flex-col' : 'flex-row')}
      data-testid="assistant-page"
    >
      {/* Mobile: a greeting + "noticed" strip above the chat (draft DF2). Placed BEFORE the chat in
          the flex-col so it sits at the top; the chat stays the stable middle child. */}
      {isMobile && <MobileAssistantHeader />}
      <div className="min-h-0 min-w-0 flex-1">
        <Chat bookId={bookId} sessionKind="assistant" className="h-full" />
      </div>
      {isMobile ? (
        <MobileAssistantDock />
      ) : (
        <div className="w-[360px] shrink-0 border-l border-border">
          <AssistantHomeStrip />
        </div>
      )}
    </div>
  );
}

export function AssistantPage() {
  return (
    <AssistantProvider>
      <AssistantPageInner />
    </AssistantProvider>
  );
}
