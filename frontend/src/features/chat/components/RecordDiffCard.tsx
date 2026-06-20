import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { FileEdit, Check, X } from 'lucide-react';
import { useAuth } from '@/auth';
import { actionsApi, type RecordEditChange } from '../actionsApi';
import { useChatStream } from '../providers';
import type { FrontendToolOutcome } from '../hooks/useChatMessages';
import type { ToolCallRecord } from '../types';

// MCP fan-out (C-PROPOSE) — the GENERIC record-edit diff card, rendered for the
// universal `propose_record_edit` tool (generalizing glossary's diff card to
// book/composition/… records). The agent proposes one OR MORE field changes on
// an existing record; the run SUSPENDS and this renders each old→new diff with
// Apply / Dismiss. Apply issues the domain's version-checked PATCH
// (If-Match: base_version → 409/412 on drift) in ONE call, then resumes with the
// REAL outcome (H6). Human-in-the-loop: nothing is written without Apply.

interface Props {
  record: ToolCallRecord;
}

interface RecordEditArgs {
  domain?: string;
  resource_ref?: Record<string, unknown>;
  base_version?: string;
  changes?: RecordEditChange[];
  rationale?: string;
}

type CardState = null | 'saved' | 'conflict' | 'error' | 'dismissed';

export function RecordDiffCard({ record }: Props) {
  const { t } = useTranslation('chat');
  const { accessToken } = useAuth();
  const { submitToolResult } = useChatStream();
  const [state, setState] = useState<CardState>(null);
  const [busy, setBusy] = useState(false);

  const args = (record.args ?? {}) as RecordEditArgs;
  const domain = args.domain ?? '';
  const resourceRef = args.resource_ref;
  const baseVersion = args.base_version;
  const changes = Array.isArray(args.changes) ? args.changes : [];

  async function resume(outcome: FrontendToolOutcome) {
    if (record.runId && record.toolCallId) {
      await submitToolResult(record.runId, record.toolCallId, outcome);
    }
  }

  async function apply() {
    if (busy || state) return;
    // A malformed proposal (schema makes this unreachable, but guard anyway)
    // must RESOLVE the suspended run, not leave the card inert.
    if (!accessToken || !domain || !resourceRef || !baseVersion || changes.length === 0) {
      setState('error');
      await resume('applied_error');
      return;
    }
    setBusy(true);
    let outcome: FrontendToolOutcome;
    try {
      await actionsApi.applyRecordEdit(domain, resourceRef, baseVersion, changes, accessToken);
      outcome = 'applied_saved';
      setState('saved');
    } catch (err) {
      const status = (err as { status?: number }).status;
      if (status === 412 || status === 409) {
        outcome = 'applied_conflict';
        setState('conflict');
        toast.error(t('recordEdit.conflict', { defaultValue: 'This changed since it was proposed — ask again to see the latest.' }));
      } else {
        outcome = 'applied_error';
        setState('error');
        toast.error(t('recordEdit.error', { defaultValue: 'Could not save the change.' }));
      }
    } finally {
      setBusy(false);
    }
    await resume(outcome);
  }

  async function dismiss() {
    if (busy || state) return;
    setBusy(true);
    setState('dismissed');
    try {
      await resume('dismissed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      data-testid="record-diff-card"
      data-domain={domain}
      className="mt-1.5 rounded-md border border-accent/30 bg-accent/5 p-2 text-xs"
    >
      <div className="mb-1 flex items-center gap-1.5 text-[11px] font-medium text-accent">
        <FileEdit className="h-3 w-3" />
        {t('recordEdit.label', { defaultValue: 'Proposed edit' })}
        {changes.length > 1 && ` · ${t('recordEdit.fields', { defaultValue: '{{count}} fields', count: changes.length })}`}
      </div>
      {args.rationale && (
        <p className="mb-1 text-[10px] text-muted-foreground">{args.rationale}</p>
      )}
      <div className="space-y-1.5">
        {changes.map((c, i) => (
          <div key={i} className="rounded bg-background/60 p-1.5 text-[11px]">
            <div className="mb-0.5 text-[10px] font-medium text-muted-foreground">
              {c.field_label ?? t('recordEdit.field', { defaultValue: 'Field' })}
            </div>
            <div className="text-foreground/60 line-through">{c.old_value || t('recordEdit.empty', { defaultValue: '(empty)' })}</div>
            <div className="font-medium text-emerald-400">{c.new_value || t('recordEdit.empty', { defaultValue: '(empty)' })}</div>
          </div>
        ))}
      </div>
      {state === null ? (
        <div className="mt-1.5 flex gap-1.5">
          <button
            type="button"
            onClick={apply}
            disabled={busy}
            className="inline-flex items-center gap-1 rounded-sm bg-accent px-2 py-0.5 text-[11px] font-medium text-accent-foreground hover:brightness-110 disabled:opacity-50"
          >
            <Check className="h-3 w-3" />{t('recordEdit.apply', { defaultValue: 'Apply' })}
          </button>
          <button
            type="button"
            onClick={dismiss}
            disabled={busy}
            className="inline-flex items-center gap-1 rounded-sm border border-border px-2 py-0.5 text-[11px] text-muted-foreground hover:text-foreground disabled:opacity-50"
          >
            <X className="h-3 w-3" />{t('recordEdit.dismiss', { defaultValue: 'Dismiss' })}
          </button>
        </div>
      ) : (
        <div className="mt-1.5 text-[10px] text-muted-foreground">
          {state === 'saved' && t('recordEdit.applied', { defaultValue: 'Applied ✓' })}
          {state === 'conflict' && t('recordEdit.conflict_short', { defaultValue: 'Changed since proposed — re-ask' })}
          {state === 'error' && t('recordEdit.error_short', { defaultValue: 'Save failed' })}
          {state === 'dismissed' && t('recordEdit.dismissed', { defaultValue: 'Dismissed' })}
        </div>
      )}
    </div>
  );
}
