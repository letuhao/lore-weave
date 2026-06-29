import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { ShieldAlert, Check, X } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { glossaryApi } from '@/features/glossary/api';
import type { ActionPreview } from '@/features/glossary/types';
import { useChatStream } from '../providers';
import { invalidateAfterConfirm } from '../utils/invalidateAfterConfirm';
import type { FrontendToolOutcome } from '../hooks/useChatMessages';
import type { ToolCallRecord } from '../types';

// Generalized class-C confirm card (spec §13.6) — supersedes the schema-only card.
// The agent proposed a high-impact action (a glossary_propose_*/glossary_book_delete
// MCP tool minted a confirm_token + descriptor), then called glossary_confirm_action;
// the run SUSPENDS and this card renders, keyed on `descriptor`. On mount it fetches a
// CURRENT-STATE preview (POST /actions/preview, non-consuming) so the human confirms
// against what is true now. Confirm POSTs the token to /v1/glossary/actions/confirm —
// the only write path, single-use — then resumes the run with the real outcome (H6).
// Never auto-applies (INV-T3/INV-5).

interface Props {
  record: ToolCallRecord;
}

interface ConfirmArgs {
  confirm_token?: string;
  descriptor?: string;
  title?: string;
}

type CardState = null | 'done' | 'expired' | 'error' | 'cancelled';

export function ConfirmCard({ record }: Props) {
  const { t } = useTranslation('chat');
  const { accessToken } = useAuth();
  const { submitToolResult } = useChatStream();
  const queryClient = useQueryClient();
  const [state, setState] = useState<CardState>(null);
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<ActionPreview | null>(null);
  // The BE's actionable reason for a 422 (e.g. "the book ontology must be adopted
  // before adding kinds"), surfaced instead of a blanket "Expired — re-ask".
  const [detail, setDetail] = useState('');

  const args = (record.args ?? {}) as ConfirmArgs;
  const token = args.confirm_token ?? '';
  const argTitle = args.title ?? '';

  // Fetch the current-state preview once on mount (synchronization, not event
  // handling). A failed/expired preview is non-fatal — the card still renders from
  // the agent-supplied title and Confirm re-validates authoritatively.
  useEffect(() => {
    let alive = true;
    if (!accessToken || !token) return;
    glossaryApi
      .previewAction(token, accessToken)
      .then((p) => {
        if (alive) setPreview(p);
      })
      .catch(() => {
        /* preview is best-effort; confirm is the source of truth */
      });
    return () => {
      alive = false;
    };
  }, [accessToken, token]);

  const title = preview?.title || argTitle;
  const rows = preview?.preview_rows ?? [];
  const destructive = preview?.destructive ?? false;

  async function resume(outcome: FrontendToolOutcome) {
    if (record.runId && record.toolCallId) {
      await submitToolResult(record.runId, record.toolCallId, outcome);
    }
  }

  async function confirm() {
    if (busy || state || !accessToken || !token) return;
    setBusy(true);
    let outcome: FrontendToolOutcome;
    try {
      await glossaryApi.confirmAction(token, accessToken);
      outcome = 'action_done';
      setState('done');
      // bug #41 — this legacy card always commits to glossary; refresh the glossary
      // browser/ontology so the change shows without an F5.
      invalidateAfterConfirm(queryClient, 'glossary');
    } catch (err) {
      const status = (err as { status?: number }).status;
      if (status === 422) {
        // expired, already-confirmed (single-use), or a precondition drift — all
        // re-proposable. Surface the BE's actionable reason instead of a blanket
        // "expired"; the card used to collapse EVERY 422 to "expired", hiding WHY
        // (e.g. "the book ontology must be adopted before adding kinds").
        outcome = 'token_expired';
        setState('expired');
        const msg = (err as Error).message;
        const meaningful = !!msg && msg !== 'Unprocessable Entity';
        setDetail(meaningful ? msg : '');
        toast.error(meaningful ? msg : t('actionConfirm.expired', { defaultValue: 'This confirmation is no longer valid — ask again to propose it afresh.' }));
      } else {
        outcome = 'action_error';
        setState('error');
        toast.error(t('actionConfirm.error', { defaultValue: 'Could not apply the change.' }));
      }
    } finally {
      setBusy(false);
    }
    await resume(outcome);
  }

  async function cancel() {
    if (busy || state) return;
    setBusy(true);
    setState('cancelled');
    try {
      await resume('cancelled');
    } finally {
      setBusy(false);
    }
  }

  const accent = destructive ? 'red' : 'amber';

  return (
    <div
      data-testid="confirm-card"
      data-descriptor={args.descriptor ?? ''}
      className={`mt-1.5 rounded-md border p-2 text-xs ${
        accent === 'red' ? 'border-red-500/40 bg-red-500/5' : 'border-amber-500/40 bg-amber-500/5'
      }`}
    >
      <div className={`mb-1 flex items-center gap-1.5 text-[11px] font-medium ${accent === 'red' ? 'text-red-500' : 'text-amber-500'}`}>
        <ShieldAlert className="h-3 w-3" />
        {title || t('actionConfirm.label', { defaultValue: 'Confirm action' })}
      </div>
      {rows.length > 0 && (
        <ul className="mb-1 space-y-0.5 text-[10px] text-foreground/90">
          {rows.map((r, i) => (
            <li key={i} className="flex justify-between gap-2">
              <span className="text-muted-foreground">{r.label}</span>
              <span>{r.value}{r.note ? ` — ${r.note}` : ''}</span>
            </li>
          ))}
        </ul>
      )}
      <p className="mb-1 text-[10px] text-muted-foreground">
        {destructive
          ? t('actionConfirm.warning_destructive', { defaultValue: 'This is destructive and cascades — please confirm.' })
          : t('actionConfirm.warning', { defaultValue: 'This change is high-impact — please confirm.' })}
      </p>
      {state === null ? (
        <div className="mt-1.5 flex gap-1.5">
          <button
            type="button"
            onClick={confirm}
            disabled={busy}
            className={`inline-flex items-center gap-1 rounded-sm px-2 py-0.5 text-[11px] font-medium text-white hover:brightness-110 disabled:opacity-50 ${
              accent === 'red' ? 'bg-red-500' : 'bg-amber-500'
            }`}
          >
            <Check className="h-3 w-3" />{t('actionConfirm.confirm', { defaultValue: 'Confirm' })}
          </button>
          <button
            type="button"
            onClick={cancel}
            disabled={busy}
            className="inline-flex items-center gap-1 rounded-sm border border-border px-2 py-0.5 text-[11px] text-muted-foreground hover:text-foreground disabled:opacity-50"
          >
            <X className="h-3 w-3" />{t('actionConfirm.cancel', { defaultValue: 'Cancel' })}
          </button>
        </div>
      ) : (
        <div className="mt-1.5 text-[10px] text-muted-foreground">
          {state === 'done' && t('actionConfirm.done', { defaultValue: 'Done ✓' })}
          {state === 'expired' && (detail || t('actionConfirm.expired_short', { defaultValue: 'Expired — re-ask' }))}
          {state === 'error' && t('actionConfirm.error_short', { defaultValue: 'Failed' })}
          {state === 'cancelled' && t('actionConfirm.cancelled', { defaultValue: 'Cancelled' })}
        </div>
      )}
    </div>
  );
}
