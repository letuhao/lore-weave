import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { ShieldAlert, Check, X } from 'lucide-react';
import { useAuth } from '@/auth';
import { actionsApi, BATCH_CONFIRM_DOMAINS } from '../actionsApi';
import { useChatStream } from '../providers';
import type { FrontendToolOutcome } from '../hooks/useChatMessages';

// #27/#29/#30 — the COALESCED confirm card. A weak local model loops single-propose
// tools, minting N confirm_tokens in ONE turn; the old UX rendered N separate cards that
// orphaned each other (confirming the first resumed/superseded the shared run, so the
// siblings could never be confirmed). This renders ONE card listing every proposed action
// with a SINGLE "Confirm all": each child token is committed (glossary via the atomic
// /actions/confirm-batch; other domains by looping the existing single /actions/confirm),
// then the suspended run — if the model DID call a frontend confirm tool — is resumed ONCE
// with the aggregate outcome. So "set up my whole schema" stays one human click, no orphans.
//
// Every child is still independently single-use + re-validated server-side at commit, so
// this never widens the human gate: one review, one click, every row re-checked.

export interface BatchChild {
  /** The confirm_token minted by a propose tool (single-use, server-validated). */
  token: string;
  /** The committing domain (glossary|book|kg|translation|composition|settings). */
  domain: string;
  descriptor?: string;
  title?: string;
}

interface Props {
  children: BatchChild[];
  /** When the model DID call a frontend confirm tool, the run suspended — resume it once
   *  after committing the whole batch so the agent learns the outcome (H6). Absent for the
   *  pure auto-confirm path (no suspend → nothing to resume). */
  resume?: { runId: string; toolCallId: string };
}

type CardState = null | 'done' | 'partial' | 'error' | 'cancelled';

export function BatchConfirmCard({ children, resume }: Props) {
  const { t } = useTranslation('chat');
  const { accessToken } = useAuth();
  const { submitToolResult } = useChatStream();
  const [state, setState] = useState<CardState>(null);
  const [busy, setBusy] = useState(false);
  const [summary, setSummary] = useState<{ applied: number; skipped: number; failed: number } | null>(null);

  const destructive = children.some(
    (c) => c.descriptor?.includes('delete') || c.descriptor === 'merge' || c.descriptor?.includes('revert'),
  );
  const accent = destructive ? 'red' : 'amber';

  async function doResume(outcome: FrontendToolOutcome) {
    if (resume?.runId && resume.toolCallId) {
      await submitToolResult(resume.runId, resume.toolCallId, outcome);
    }
  }

  async function confirmAll() {
    if (busy || state || !accessToken) return;
    setBusy(true);
    // Group by domain so a domain WITH the atomic batch endpoint commits in one call,
    // while a domain without one loops the existing single-confirm — every domain works.
    const byDomain = new Map<string, BatchChild[]>();
    for (const c of children) {
      const g = byDomain.get(c.domain);
      if (g) g.push(c);
      else byDomain.set(c.domain, [c]);
    }
    let applied = 0;
    let skipped = 0;
    let failed = 0;
    for (const [domain, group] of byDomain) {
      if (BATCH_CONFIRM_DOMAINS.has(domain)) {
        try {
          const res = await actionsApi.confirmActionBatch(domain, group.map((c) => c.token), accessToken);
          applied += res.applied;
          skipped += res.skipped;
          failed += res.failed;
        } catch {
          failed += group.length;
        }
      } else {
        // No batch endpoint for this domain — loop the single-confirm (same single-use,
        // server-validated path each separate card would have used).
        for (const c of group) {
          try {
            await actionsApi.confirmAction(domain, c.token, accessToken);
            applied += 1;
          } catch {
            failed += 1;
          }
        }
      }
    }
    setSummary({ applied, skipped, failed });
    const outcome: FrontendToolOutcome = applied > 0 ? 'action_done' : 'action_error';
    setState(failed === 0 ? 'done' : applied > 0 ? 'partial' : 'error');
    if (failed === 0) {
      toast.success(t('batchConfirm.applied', { defaultValue: 'Applied {{count}} actions', count: applied }));
    } else {
      toast.error(t('batchConfirm.partial', {
        defaultValue: 'Applied {{applied}}, {{failed}} failed — ask again to retry the rest.',
        applied,
        failed,
      }));
    }
    setBusy(false);
    await doResume(outcome);
  }

  async function cancel() {
    if (busy || state) return;
    setBusy(true);
    setState('cancelled');
    try {
      await doResume('cancelled');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      data-testid="batch-confirm-card"
      data-count={children.length}
      className={`mt-1.5 rounded-md border p-2 text-xs ${
        accent === 'red' ? 'border-red-500/40 bg-red-500/5' : 'border-amber-500/40 bg-amber-500/5'
      }`}
    >
      <div className={`mb-1 flex items-center gap-1.5 text-[11px] font-medium ${accent === 'red' ? 'text-red-500' : 'text-amber-500'}`}>
        <ShieldAlert className="h-3 w-3" />
        {t('batchConfirm.title', { defaultValue: 'Confirm {{count}} actions in one step', count: children.length })}
      </div>

      <ul data-testid="batch-confirm-rows" className="mb-1 max-h-44 space-y-0.5 overflow-y-auto text-[10px] text-foreground/90">
        {children.map((c, i) => (
          <li key={c.token.slice(0, 24) + i} className="flex items-center gap-1.5 rounded bg-background/60 px-1.5 py-0.5">
            <span className="text-muted-foreground">{i + 1}.</span>
            <span className="truncate">{c.title || c.descriptor || t('batchConfirm.action', { defaultValue: 'action' })}</span>
            <span className="ml-auto shrink-0 text-[9px] uppercase text-muted-foreground/70">{c.domain}</span>
          </li>
        ))}
      </ul>

      <p className="mb-1 text-[10px] text-muted-foreground">
        {destructive
          ? t('batchConfirm.warning_destructive', { defaultValue: 'Some of these are destructive — review before confirming.' })
          : t('batchConfirm.warning', { defaultValue: 'These high-impact changes apply together on confirm.' })}
      </p>

      {state === null ? (
        <div className="mt-1.5 flex gap-1.5">
          <button
            type="button"
            onClick={confirmAll}
            disabled={busy}
            className={`inline-flex items-center gap-1 rounded-sm px-2 py-0.5 text-[11px] font-medium text-white hover:brightness-110 disabled:opacity-50 ${
              accent === 'red' ? 'bg-red-500' : 'bg-amber-500'
            }`}
          >
            <Check className="h-3 w-3" />
            {t('batchConfirm.confirm_all', { defaultValue: 'Confirm all' })}
          </button>
          <button
            type="button"
            onClick={cancel}
            disabled={busy}
            className="inline-flex items-center gap-1 rounded-sm border border-border px-2 py-0.5 text-[11px] text-muted-foreground hover:text-foreground disabled:opacity-50"
          >
            <X className="h-3 w-3" />
            {t('batchConfirm.cancel', { defaultValue: 'Cancel' })}
          </button>
        </div>
      ) : (
        <div data-testid="batch-confirm-result" className="mt-1.5 text-[10px] text-muted-foreground">
          {state === 'done' && t('batchConfirm.done', { defaultValue: 'Applied {{count}} ✓', count: summary?.applied ?? 0 })}
          {state === 'partial' && t('batchConfirm.partial_short', {
            defaultValue: 'Applied {{applied}}, {{failed}} failed',
            applied: summary?.applied ?? 0,
            failed: summary?.failed ?? 0,
          })}
          {state === 'error' && t('batchConfirm.error_short', { defaultValue: 'Could not apply — re-ask' })}
          {state === 'cancelled' && t('batchConfirm.cancelled', { defaultValue: 'Cancelled' })}
        </div>
      )}
    </div>
  );
}
