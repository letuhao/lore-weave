import { useState } from 'react';
import { Check, Sparkles, X } from 'lucide-react';
import { toast } from 'sonner';
import type { PendingFact, PendingFactType } from '../types';

// K21-C (D8 / K21.7 sf4): the pending-facts review card.
//
// Rendered below the chat message list. Shows each fact the
// assistant's `memory_remember` tool queued for confirmation
// (knowledge-service design D6) with Confirm / Reject buttons wired
// to the D7 endpoints. Renders nothing when the list is empty, so
// ChatView can mount it unconditionally.
//
// View-only per CLAUDE.md MVC rules: usePendingFacts owns the query +
// the confirm/reject mutations; this component just renders and calls
// the passed-in actions. The only local state is `actingId` — which
// row's button was clicked — so the row can show a per-row pending
// state without all rows freezing.

interface Props {
  pendingFacts: PendingFact[];
  /** Confirm the fact (write to graph). From usePendingFacts. */
  onConfirm: (pendingFactId: string) => Promise<void>;
  /** Reject the fact (drop it). From usePendingFacts. */
  onReject: (pendingFactId: string) => Promise<void>;
}

// fact_type → a short human label for the row badge.
const FACT_TYPE_LABELS: Record<PendingFactType, string> = {
  decision: 'Decision',
  preference: 'Preference',
  milestone: 'Milestone',
  negation: 'Correction',
};

export function PendingFactsCard({ pendingFacts, onConfirm, onReject }: Props) {
  // Which row currently has an action in flight. Lets one row show a
  // disabled/pending state without freezing the others.
  const [actingId, setActingId] = useState<string | null>(null);

  // Empty list → nothing to review. Render nothing so the parent
  // doesn't need its own guard.
  if (pendingFacts.length === 0) return null;

  async function run(
    id: string,
    action: (id: string) => Promise<void>,
    failMsg: string,
  ) {
    setActingId(id);
    try {
      await action(id);
    } catch (err) {
      toast.error(`${failMsg}: ${(err as Error).message}`);
    } finally {
      setActingId(null);
    }
  }

  return (
    <div
      data-testid="pending-facts-card"
      className="mx-auto w-full max-w-full px-4 pb-3 md:max-w-[720px] 2xl:max-w-[900px]"
    >
      <div className="rounded-lg border border-primary/25 bg-primary/5 p-3">
        <div className="mb-2 flex items-center gap-1.5">
          <Sparkles className="h-3.5 w-3.5 text-primary" />
          <span className="text-xs font-semibold text-foreground">
            Memories awaiting your confirmation
          </span>
        </div>

        <ul className="space-y-1.5">
          {pendingFacts.map((fact) => {
            const busy = actingId === fact.pending_fact_id;
            return (
              <li
                key={fact.pending_fact_id}
                data-testid="pending-fact-row"
                className="flex items-start gap-2 rounded-md border border-border bg-card px-2.5 py-2"
              >
                <span className="mt-0.5 shrink-0 rounded-sm border border-primary/20 bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary">
                  {FACT_TYPE_LABELS[fact.fact_type] ?? fact.fact_type}
                </span>
                <p className="min-w-0 flex-1 break-words text-xs text-foreground/90">
                  {fact.fact_text}
                </p>
                <div className="flex shrink-0 items-center gap-1">
                  <button
                    type="button"
                    data-testid="pending-fact-confirm"
                    disabled={busy}
                    onClick={() =>
                      run(fact.pending_fact_id, onConfirm, 'Confirm failed')
                    }
                    title="Confirm — save this memory"
                    className="flex items-center gap-1 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-2 py-1 text-[11px] font-medium text-emerald-400 transition-colors hover:bg-emerald-500/20 disabled:opacity-50"
                  >
                    <Check className="h-3 w-3" />
                    Confirm
                  </button>
                  <button
                    type="button"
                    data-testid="pending-fact-reject"
                    disabled={busy}
                    onClick={() =>
                      run(fact.pending_fact_id, onReject, 'Reject failed')
                    }
                    title="Reject — discard this memory"
                    className="flex items-center gap-1 rounded-md border border-border px-2 py-1 text-[11px] font-medium text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:opacity-50"
                  >
                    <X className="h-3 w-3" />
                    Reject
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
