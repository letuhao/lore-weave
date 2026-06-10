import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { BookText, Check, X } from 'lucide-react';
import { useAuth } from '@/auth';
import { glossaryApi } from '@/features/glossary/api';
import { useChatStream } from '../providers';
import type { FrontendToolOutcome } from '../hooks/useChatMessages';
import type { ToolCallRecord } from '../types';

// Glossary-assistant P3 + EDIT-ATOMIC — the edit-existing proposal card (shared,
// mounted on every book-scoped surface). The agent calls
// glossary_propose_entity_edit with one OR MORE field changes; the run SUSPENDS,
// and this card renders each proposed old→new diff with Apply / Dismiss. Apply
// issues ONE version-checked atomic write (apply-edit: base_version → 412 on
// drift, all changes in one tx, H5), then resumes the run with the REAL outcome
// (H6). Human-in-the-loop: nothing reaches canon without Apply (INV-1).

interface Props {
  record: ToolCallRecord;
}

interface GlossaryEditChange {
  target?: 'short_description' | 'attribute';
  attr_value_id?: string;
  field_label?: string;
  old_value?: string;
  new_value?: string;
}

interface GlossaryEditArgs {
  book_id?: string;
  entity_id?: string;
  base_version?: string;
  changes?: GlossaryEditChange[];
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
  const { book_id, entity_id, base_version } = args;
  const changes = Array.isArray(args.changes) ? args.changes : [];

  async function resume(outcome: FrontendToolOutcome) {
    if (record.runId && record.toolCallId) {
      await submitToolResult(record.runId, record.toolCallId, outcome);
    }
  }

  async function apply() {
    if (busy || state) return;
    // EDIT-LOW2: a malformed proposal (schema makes this unreachable, but guard
    // anyway) must RESOLVE the suspended run, not leave the card inert.
    if (!accessToken || !book_id || !entity_id || !base_version || changes.length === 0) {
      setState('error');
      await resume('applied_error');
      return;
    }
    setBusy(true);
    let outcome: FrontendToolOutcome;
    try {
      // Build ONE atomic apply-edit body from the changes (short_description +
      // attribute updates) — applied in a single tx with one version check.
      const body: {
        base_version: string;
        short_description?: string;
        attributes?: { attr_value_id: string; original_value: string }[];
      } = { base_version };
      const attributes: { attr_value_id: string; original_value: string }[] = [];
      for (const c of changes) {
        if (c.target === 'attribute') {
          if (!c.attr_value_id) throw new Error('missing attr_value_id');
          attributes.push({ attr_value_id: c.attr_value_id, original_value: c.new_value ?? '' });
        } else {
          body.short_description = c.new_value ?? '';
        }
      }
      if (attributes.length > 0) body.attributes = attributes;
      await glossaryApi.applyEntityEdit(book_id, entity_id, body, accessToken);
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
        {t('glossaryEdit.label', { defaultValue: 'Glossary edit' })}
        {changes.length > 1 && ` · ${t('glossaryEdit.fields', { defaultValue: '{{count}} fields', count: changes.length })}`}
      </div>
      {args.rationale && (
        <p className="mb-1 text-[10px] text-muted-foreground">{args.rationale}</p>
      )}
      <div className="space-y-1.5">
        {changes.map((c, i) => (
          <div key={i} className="rounded bg-background/60 p-1.5 text-[11px]">
            <div className="mb-0.5 text-[10px] font-medium text-muted-foreground">
              {c.field_label ?? t('glossaryEdit.field', { defaultValue: 'Field' })}
            </div>
            <div className="text-foreground/60 line-through">{c.old_value || t('glossaryEdit.empty', { defaultValue: '(empty)' })}</div>
            <div className="font-medium text-emerald-400">{c.new_value || t('glossaryEdit.empty', { defaultValue: '(empty)' })}</div>
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
