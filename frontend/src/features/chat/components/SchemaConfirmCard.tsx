import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { ShieldAlert, Check, X } from 'lucide-react';
import { useAuth } from '@/auth';
import { glossaryApi } from '@/features/glossary/api';
import { useChatStream } from '../providers';
import type { FrontendToolOutcome } from '../hooks/useChatMessages';
import type { ToolCallRecord } from '../types';

// Glossary-assistant P4 — the Tier-S schema-confirm card (shared). The agent
// proposed a new kind/attribute (glossary_propose_new_* minted a confirm_token),
// then called glossary_confirm_schema; the run SUSPENDS and this card renders the
// preview with a Confirm/Cancel. Confirm POSTs the token to the JWT-only
// /v1/glossary/schema/confirm — the ONLY schema-create path (INV-9/H8) — then
// resumes the run with the real outcome (H6). Schema changes are high-impact, so
// the copy makes the blast radius explicit and never auto-applies (INV-5).

interface Props {
  record: ToolCallRecord;
}

interface ConfirmArgs {
  confirm_token?: string;
  op?: 'kind' | 'attribute';
  summary?: string;
}

type CardState = null | 'created' | 'expired' | 'error' | 'cancelled';

export function SchemaConfirmCard({ record }: Props) {
  const { t } = useTranslation('chat');
  const { accessToken } = useAuth();
  const { submitToolResult } = useChatStream();
  const [state, setState] = useState<CardState>(null);
  const [busy, setBusy] = useState(false);

  const args = (record.args ?? {}) as ConfirmArgs;
  const token = args.confirm_token ?? '';
  const op = args.op ?? 'kind';
  const summary = args.summary ?? '';

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
      await glossaryApi.confirmSchema(token, accessToken);
      outcome = 'schema_created';
      setState('created');
    } catch (err) {
      const status = (err as { status?: number }).status;
      if (status === 422) {
        outcome = 'token_expired';
        setState('expired');
        toast.error(t('schemaConfirm.expired', { defaultValue: 'This confirmation expired — ask again to propose it afresh.' }));
      } else {
        outcome = 'schema_error';
        setState('error');
        toast.error(t('schemaConfirm.error', { defaultValue: 'Could not create the schema change.' }));
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

  return (
    <div
      data-testid="schema-confirm-card"
      className="mt-1.5 rounded-md border border-amber-500/40 bg-amber-500/5 p-2 text-xs"
    >
      <div className="mb-1 flex items-center gap-1.5 text-[11px] font-medium text-amber-500">
        <ShieldAlert className="h-3 w-3" />
        {op === 'attribute'
          ? t('schemaConfirm.attr_label', { defaultValue: 'Confirm new attribute' })
          : t('schemaConfirm.kind_label', { defaultValue: 'Confirm new kind' })}
      </div>
      <p className="mb-1 text-[11px] text-foreground/90">{summary}</p>
      <p className="mb-1 text-[10px] text-muted-foreground">
        {t('schemaConfirm.warning', { defaultValue: 'Schema changes affect every book — please confirm.' })}
      </p>
      {state === null ? (
        <div className="mt-1.5 flex gap-1.5">
          <button
            type="button"
            onClick={confirm}
            disabled={busy}
            className="inline-flex items-center gap-1 rounded-sm bg-amber-500 px-2 py-0.5 text-[11px] font-medium text-white hover:brightness-110 disabled:opacity-50"
          >
            <Check className="h-3 w-3" />{t('schemaConfirm.confirm', { defaultValue: 'Confirm' })}
          </button>
          <button
            type="button"
            onClick={cancel}
            disabled={busy}
            className="inline-flex items-center gap-1 rounded-sm border border-border px-2 py-0.5 text-[11px] text-muted-foreground hover:text-foreground disabled:opacity-50"
          >
            <X className="h-3 w-3" />{t('schemaConfirm.cancel', { defaultValue: 'Cancel' })}
          </button>
        </div>
      ) : (
        <div className="mt-1.5 text-[10px] text-muted-foreground">
          {state === 'created' && t('schemaConfirm.created', { defaultValue: 'Created ✓' })}
          {state === 'expired' && t('schemaConfirm.expired_short', { defaultValue: 'Expired — re-ask' })}
          {state === 'error' && t('schemaConfirm.error_short', { defaultValue: 'Failed' })}
          {state === 'cancelled' && t('schemaConfirm.cancelled', { defaultValue: 'Cancelled' })}
        </div>
      )}
    </div>
  );
}
