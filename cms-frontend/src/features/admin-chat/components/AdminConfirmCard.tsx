// T4d — the System-tier confirm card. The admin agent proposed a System write
// (glossary_admin_propose_*), which minted a confirm_token + descriptor and
// suspended on glossary_confirm_action. This card renders for that pending tool
// record. On mount it fetches a non-consuming current-state preview; on Confirm
// it POSTs the token to /v1/glossary/actions/admin/confirm (the ADMIN endpoint,
// NOT the user /actions/confirm — keyed by the descriptor's admin authority),
// then resumes the run with the real outcome (H6 truthful resume). Never
// auto-applies (INV-T3).
import { useEffect, useState } from 'react';
import { ShieldAlert, Check, X } from 'lucide-react';
import { useAuth } from '@/auth';
import { adminChatApi } from '../api';
import type { ActionPreview, AdminToolOutcome, ToolCallRecord } from '../types';

interface Props {
  record: ToolCallRecord;
  onResume: (runId: string, toolCallId: string, outcome: AdminToolOutcome) => void;
}

interface ConfirmArgs {
  confirm_token?: string;
  descriptor?: string;
  title?: string;
}

type CardState = null | 'done' | 'expired' | 'error' | 'cancelled';

export function AdminConfirmCard({ record, onResume }: Props) {
  const { accessToken } = useAuth(); // RS256 admin token — the admin-confirm bearer.
  const [state, setState] = useState<CardState>(null);
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<ActionPreview | null>(null);

  const args = (record.args ?? {}) as ConfirmArgs;
  const token = args.confirm_token ?? '';
  const argTitle = args.title ?? '';

  useEffect(() => {
    let alive = true;
    if (!accessToken || !token) return;
    adminChatApi
      .previewAdminAction(token, accessToken)
      .then((p) => {
        if (alive) setPreview(p);
      })
      .catch(() => {
        /* preview is best-effort; confirm re-validates authoritatively */
      });
    return () => {
      alive = false;
    };
  }, [accessToken, token]);

  const title = preview?.title || argTitle;
  const rows = preview?.preview_rows ?? [];
  const destructive = preview?.destructive ?? false;
  const done = state !== null || record.pending === false;

  async function confirm() {
    if (busy || done || !accessToken || !token || !record.runId || !record.toolCallId) return;
    setBusy(true);
    let outcome: AdminToolOutcome;
    try {
      await adminChatApi.confirmAdminAction(token, accessToken);
      outcome = 'action_done';
      setState('done');
    } catch (err) {
      const status = (err as { status?: number }).status;
      if (status === 422) {
        outcome = 'token_expired';
        setState('expired');
      } else {
        outcome = 'action_error';
        setState('error');
      }
    } finally {
      setBusy(false);
    }
    onResume(record.runId, record.toolCallId, outcome);
  }

  function cancel() {
    if (busy || done || !record.runId || !record.toolCallId) return;
    setState('cancelled');
    onResume(record.runId, record.toolCallId, 'cancelled');
  }

  const accent = destructive ? 'red' : 'amber';

  return (
    <div
      data-testid="admin-confirm-card"
      data-descriptor={args.descriptor ?? ''}
      className={`mt-1.5 rounded-md border p-2 text-xs ${
        accent === 'red' ? 'border-red-500/40 bg-red-500/5' : 'border-amber-500/40 bg-amber-500/5'
      }`}
    >
      <div
        className={`mb-1 flex items-center gap-1.5 text-[11px] font-medium ${
          accent === 'red' ? 'text-red-500' : 'text-amber-500'
        }`}
      >
        <ShieldAlert className="h-3 w-3" />
        {title || 'Confirm System change'}
      </div>
      {rows.length > 0 && (
        <ul className="mb-1 space-y-0.5 text-[10px] text-foreground/90">
          {rows.map((r, i) => (
            <li key={i} className="flex justify-between gap-2">
              <span className="text-muted-foreground">{r.label}</span>
              <span>
                {r.value}
                {r.note ? ` — ${r.note}` : ''}
              </span>
            </li>
          ))}
        </ul>
      )}
      <p className="mb-1 text-[10px] text-muted-foreground">
        This is a System-tier change — it affects every tenant. Please confirm.
      </p>
      {state === null && record.pending !== false ? (
        <div className="mt-1.5 flex gap-1.5">
          <button
            type="button"
            onClick={confirm}
            disabled={busy}
            className={`inline-flex items-center gap-1 rounded-sm px-2 py-0.5 text-[11px] font-medium text-white hover:brightness-110 disabled:opacity-50 ${
              accent === 'red' ? 'bg-red-500' : 'bg-amber-500'
            }`}
          >
            <Check className="h-3 w-3" />
            Confirm
          </button>
          <button
            type="button"
            onClick={cancel}
            disabled={busy}
            className="inline-flex items-center gap-1 rounded-sm border border-border px-2 py-0.5 text-[11px] text-muted-foreground hover:text-foreground disabled:opacity-50"
          >
            <X className="h-3 w-3" />
            Cancel
          </button>
        </div>
      ) : (
        <div className="mt-1.5 text-[10px] text-muted-foreground">
          {state === 'done' && 'Done ✓'}
          {state === 'expired' && 'Expired — ask again'}
          {state === 'error' && 'Failed'}
          {state === 'cancelled' && 'Cancelled'}
          {state === null && 'Resolved'}
        </div>
      )}
    </div>
  );
}
