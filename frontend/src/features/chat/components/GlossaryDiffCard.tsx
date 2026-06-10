import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { BookText, Check, X } from 'lucide-react';
import { useAuth } from '@/auth';
import { glossaryApi } from '@/features/glossary/api';
import { useChatStream } from '../providers';
import type { FrontendToolOutcome } from '../hooks/useChatMessages';
import type { ToolCallRecord } from '../types';

// Glossary-assistant P3 — the edit-existing proposal card (shared, mounted on
// every book-scoped surface). The agent calls glossary_propose_entity_edit, the
// run SUSPENDS, and this card renders the proposed old→new diff with Apply /
// Dismiss. Apply issues a version-checked PATCH (If-Match: base_version → 412 on
// drift, H5), then resumes the run with the REAL outcome (H6) so the agent only
// claims success on applied_saved. Human-in-the-loop: nothing reaches canon
// without Apply (INV-1).

interface Props {
  record: ToolCallRecord;
}

interface GlossaryEditArgs {
  book_id?: string;
  entity_id?: string;
  base_version?: string;
  target?: 'short_description' | 'attribute';
  attr_value_id?: string;
  field_label?: string;
  old_value?: string;
  new_value?: string;
  rationale?: string;
}

type CardState = null | 'saved' | 'conflict' | 'error' | 'dismissed';

export function GlossaryDiffCard({ record }: Props) {
  const { t } = useTranslation('chat');
  const { accessToken } = useAuth();
  const { submitToolResult } = useChatStream();
  const [state, setState] = useState<CardState>(null);
  const [busy, setBusy] = useState(false);

  const args = (record.args ?? {}) as GlossaryEditArgs;
  const { book_id, entity_id, base_version, target, attr_value_id } = args;
  const oldValue = args.old_value ?? '';
  const newValue = args.new_value ?? '';
  const label = args.field_label ?? t('glossaryEdit.field', { defaultValue: 'Field' });

  async function resume(outcome: FrontendToolOutcome) {
    if (record.runId && record.toolCallId) {
      await submitToolResult(record.runId, record.toolCallId, outcome);
    }
  }

  async function apply() {
    if (busy || state || !accessToken || !book_id || !entity_id || !base_version) return;
    setBusy(true);
    let outcome: FrontendToolOutcome;
    try {
      if (target === 'attribute') {
        if (!attr_value_id) throw new Error('missing attr_value_id');
        await glossaryApi.patchAttributeValue(
          book_id, entity_id, attr_value_id, { original_value: newValue }, accessToken,
          { ifMatch: base_version },
        );
      } else {
        await glossaryApi.patchEntity(
          book_id, entity_id, { short_description: newValue }, accessToken,
          { ifMatch: base_version },
        );
      }
      outcome = 'applied_saved';
      setState('saved');
    } catch (err) {
      const status = (err as { status?: number }).status;
      if (status === 412 || status === 409) {
        outcome = 'applied_conflict';
        setState('conflict');
        toast.error(t('glossaryEdit.conflict', { defaultValue: 'This entity changed since it was proposed — ask again to see the latest.' }));
      } else {
        outcome = 'applied_error';
        setState('error');
        toast.error(t('glossaryEdit.error', { defaultValue: 'Could not save the change.' }));
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
      data-testid="glossary-diff-card"
      className="mt-1.5 rounded-md border border-accent/30 bg-accent/5 p-2 text-xs"
    >
      <div className="mb-1 flex items-center gap-1.5 text-[11px] font-medium text-accent">
        <BookText className="h-3 w-3" />
        {t('glossaryEdit.label', { defaultValue: 'Glossary edit' })} · {label}
      </div>
      {args.rationale && (
        <p className="mb-1 text-[10px] text-muted-foreground">{args.rationale}</p>
      )}
      <div className="space-y-1 rounded bg-background/60 p-1.5 text-[11px]">
        <div className="text-foreground/60 line-through">{oldValue || t('glossaryEdit.empty', { defaultValue: '(empty)' })}</div>
        <div className="font-medium text-emerald-400">{newValue || t('glossaryEdit.empty', { defaultValue: '(empty)' })}</div>
      </div>
      {state === null ? (
        <div className="mt-1.5 flex gap-1.5">
          <button
            type="button"
            onClick={apply}
            disabled={busy}
            className="inline-flex items-center gap-1 rounded-sm bg-accent px-2 py-0.5 text-[11px] font-medium text-accent-foreground hover:brightness-110 disabled:opacity-50"
          >
            <Check className="h-3 w-3" />{t('glossaryEdit.apply', { defaultValue: 'Apply' })}
          </button>
          <button
            type="button"
            onClick={dismiss}
            disabled={busy}
            className="inline-flex items-center gap-1 rounded-sm border border-border px-2 py-0.5 text-[11px] text-muted-foreground hover:text-foreground disabled:opacity-50"
          >
            <X className="h-3 w-3" />{t('glossaryEdit.dismiss', { defaultValue: 'Dismiss' })}
          </button>
        </div>
      ) : (
        <div className="mt-1.5 text-[10px] text-muted-foreground">
          {state === 'saved' && t('glossaryEdit.applied', { defaultValue: 'Applied ✓' })}
          {state === 'conflict' && t('glossaryEdit.conflict_short', { defaultValue: 'Changed since proposed — re-ask' })}
          {state === 'error' && t('glossaryEdit.error_short', { defaultValue: 'Save failed' })}
          {state === 'dismissed' && t('glossaryEdit.dismissed', { defaultValue: 'Dismissed' })}
        </div>
      )}
    </div>
  );
}
