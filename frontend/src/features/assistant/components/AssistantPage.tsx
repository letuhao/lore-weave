// WS-1.10 — the /assistant route. Provisions the diary + assistant project on open (idempotent),
// then lays out the reused chat surface (left) beside the home strip (right). The chat is the SAME
// features/chat surface (spec 02 D12 — "not a new surface"), bound to the diary book + stamped
// session_kind='assistant' so recall + capture gate on it.
import { Chat } from '@/features/chat/Chat';
import { AssistantProvider, useAssistant } from '../context/AssistantContext';
import { AssistantHomeStrip } from './AssistantHomeStrip';

function AssistantPageInner() {
  const { loading, error, provisioned, bookId, reprovision } = useAssistant();

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center" data-testid="assistant-loading">
        <p className="text-sm text-muted-foreground">Setting up your assistant…</p>
      </div>
    );
  }

  if (error || !provisioned || !bookId) {
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

  return (
    <div className="flex h-full min-h-0" data-testid="assistant-page">
      <div className="min-w-0 flex-1">
        <Chat bookId={bookId} sessionKind="assistant" className="h-full" />
      </div>
      <div className="hidden w-[360px] shrink-0 border-l border-border md:block">
        <AssistantHomeStrip />
      </div>
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
