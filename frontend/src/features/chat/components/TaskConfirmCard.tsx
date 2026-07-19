import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Check, ShieldAlert, X } from 'lucide-react';
import { useChatStream } from '../providers';
import type { ToolCallRecord } from '../types';

// ext-tasks (T1c(3)) — the durable-gate confirm card. A capability-gated domain tool
// opened a task-shaped human gate (e.g. composition_create_derivative → spawn a dị
// bản): the run SUSPENDED holding a durable task at `input_required`, and this card
// renders its `inputRequests` (title/preview). Confirm resumes the run with an accept
// outcome → chat-service drives the domain's provide-input tool, which runs the REAL
// write and returns the result; Dismiss cancels. Nothing is written until Confirm
// (INV-1). Distinct from ConfirmActionCard: the gate is a durable TASK the domain owns
// (resumed via /tool-results), not a confirm_token replayed to /actions/confirm.

interface Props {
  record: ToolCallRecord;
}

interface InputRequests {
  title?: string;
  descriptor?: string;
  domain?: string;
  preview?: string;
}

type CardState = null | 'done' | 'cancelled' | 'error';

export function TaskConfirmCard({ record }: Props) {
  const { t } = useTranslation('chat');
  const { submitToolResult } = useChatStream();
  const [state, setState] = useState<CardState>(null);
  const [busy, setBusy] = useState(false);

  const task = record.task ?? null;
  const ir = (task?.inputRequests ?? {}) as InputRequests;
  const title = ir.title || t('taskGate.defaultTitle', { defaultValue: 'Confirm this action?' });

  async function resume(outcome: string) {
    if (record.runId && record.toolCallId) {
      await submitToolResult(record.runId, record.toolCallId, outcome);
    }
  }

  async function confirm() {
    if (busy || state || !task) return;
    setBusy(true);
    try {
      // 'action_done' is an accept outcome — chat-service resume drives the domain's
      // provide-input tool (accepted=true), which runs the real write.
      await resume('action_done');
      setState('done');
    } catch {
      setState('error');
    } finally {
      setBusy(false);
    }
  }

  async function dismiss() {
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
      data-testid="task-confirm-card"
      className="mt-1.5 rounded-md border border-amber-500/30 bg-amber-500/5 p-2 text-xs"
    >
      <div className="mb-1 flex items-center gap-1.5 text-[11px] font-medium text-amber-500">
        <ShieldAlert className="h-3 w-3" />
        {t('taskGate.label', { defaultValue: 'Confirm' })}
      </div>
      <p className="mb-1.5 text-foreground">{title}</p>
      {ir.preview && (
        <p className="mb-1.5 whitespace-pre-wrap text-[10px] text-muted-foreground">{ir.preview}</p>
      )}
      {state === null ? (
        <div className="mt-1.5 flex gap-1.5">
          <button
            type="button"
            data-testid="task-confirm"
            onClick={confirm}
            disabled={busy}
            className="inline-flex items-center gap-1 rounded-sm bg-amber-500 px-2 py-0.5 text-[11px] font-medium text-amber-950 hover:brightness-110 disabled:opacity-50"
          >
            <Check className="h-3 w-3" />
            {t('taskGate.confirm', { defaultValue: 'Confirm' })}
          </button>
          <button
            type="button"
            data-testid="task-dismiss"
            onClick={dismiss}
            disabled={busy}
            className="inline-flex items-center gap-1 rounded-sm border border-border px-2 py-0.5 text-[11px] text-muted-foreground hover:text-foreground disabled:opacity-50"
          >
            <X className="h-3 w-3" />
            {t('taskGate.dismiss', { defaultValue: 'Dismiss' })}
          </button>
        </div>
      ) : (
        <div className="mt-1.5 text-[10px] text-muted-foreground">
          {state === 'done' && t('taskGate.done', { defaultValue: 'Confirmed ✓' })}
          {state === 'cancelled' && t('taskGate.cancelled', { defaultValue: 'Dismissed' })}
          {state === 'error' && t('taskGate.error', { defaultValue: 'Could not confirm' })}
        </div>
      )}
    </div>
  );
}
