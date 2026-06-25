import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Sparkles, Check, X } from 'lucide-react';
import { getEditorTarget } from '../context/editorBridge';
import { useChatStream } from '../providers';
import type { ToolCallRecord } from '../types';

// ARCH-1 C6 — the editor write-back proposal card.
//
// When the agent calls the propose_edit frontend tool, the turn suspends and the
// assistant message carries a pending tool record (with the proposal args). This
// card renders the proposed text + Apply/Dismiss. Apply writes into the open
// Tiptap doc via the editor bridge (only if the proposal targets the open
// chapter), then resumes the agent's run with the outcome; Dismiss resumes with
// "dismissed". Human-in-the-loop: nothing touches the document without Apply.

interface Props {
  record: ToolCallRecord;
  /** the chapter the chat panel is bound to — used to guard cross-chapter edits */
  chapterId?: string;
}

interface ProposeArgs {
  operation?: 'insert_at_cursor' | 'replace_selection';
  text?: string;
  rationale?: string;
}

export function ProposeEditCard({ record, chapterId }: Props) {
  const { t } = useTranslation('chat');
  const { submitToolResult } = useChatStream();
  const [done, setDone] = useState<null | 'applied' | 'dismissed'>(null);
  const [busy, setBusy] = useState(false);

  const args = (record.args ?? {}) as ProposeArgs;
  const text = args.text ?? '';
  const operation = args.operation ?? 'insert_at_cursor';

  async function apply() {
    if (busy || done) return;
    const target = getEditorTarget();
    if (!target) {
      toast.error(t('propose.no_editor', { defaultValue: 'Open the chapter to apply this edit.' }));
      return;
    }
    // Chapter-match guard — never write a proposal into a different document.
    if (chapterId && target.chapterId !== chapterId) {
      toast.error(t('propose.wrong_chapter', { defaultValue: 'This suggestion was for a different chapter.' }));
      return;
    }
    // T5.3 — chat-proposed edits are AI prose; tag them so they carry the
    // unreviewed-AI provenance mark like co-writer insertions.
    const prov = { source: 'ai', status: 'unreviewed' as const, ts: new Date().toISOString() };
    let ok = false;
    if (operation === 'replace_selection') {
      ok = target.handle.replaceSelection(text, prov);
      if (!ok) {
        toast.error(t('propose.no_selection', { defaultValue: 'Select the text to replace, then Apply.' }));
        return;
      }
    } else {
      ok = target.handle.insertAtCursor(text, prov);
      if (!ok) {
        toast.error(t('propose.apply_failed', { defaultValue: 'Could not apply the edit.' }));
        return;
      }
    }
    setBusy(true);
    setDone('applied');
    try {
      if (record.runId && record.toolCallId) {
        await submitToolResult(record.runId, record.toolCallId, 'applied', text);
      }
    } finally {
      setBusy(false);
    }
  }

  async function dismiss() {
    if (busy || done) return;
    setBusy(true);
    setDone('dismissed');
    try {
      if (record.runId && record.toolCallId) {
        await submitToolResult(record.runId, record.toolCallId, 'dismissed');
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      data-testid="propose-edit-card"
      className="mt-1.5 rounded-md border border-accent/30 bg-accent/5 p-2 text-xs"
    >
      <div className="mb-1 flex items-center gap-1.5 text-[11px] font-medium text-accent">
        <Sparkles className="h-3 w-3" />
        {operation === 'replace_selection'
          ? t('propose.replace_label', { defaultValue: 'Suggested rewrite' })
          : t('propose.insert_label', { defaultValue: 'Suggested insertion' })}
      </div>
      {args.rationale && (
        <p className="mb-1 text-[10px] text-muted-foreground">{args.rationale}</p>
      )}
      <pre className="max-h-40 overflow-y-auto whitespace-pre-wrap rounded bg-background/60 p-1.5 font-sans text-[11px] text-foreground/90">
        {text}
      </pre>
      {done === null ? (
        <div className="mt-1.5 flex gap-1.5">
          <button
            type="button"
            onClick={apply}
            disabled={busy}
            className="inline-flex items-center gap-1 rounded-sm bg-accent px-2 py-0.5 text-[11px] font-medium text-accent-foreground hover:brightness-110 disabled:opacity-50"
          >
            <Check className="h-3 w-3" />{t('propose.apply', { defaultValue: 'Apply' })}
          </button>
          <button
            type="button"
            onClick={dismiss}
            disabled={busy}
            className="inline-flex items-center gap-1 rounded-sm border border-border px-2 py-0.5 text-[11px] text-muted-foreground hover:text-foreground disabled:opacity-50"
          >
            <X className="h-3 w-3" />{t('propose.dismiss', { defaultValue: 'Dismiss' })}
          </button>
        </div>
      ) : (
        <div className="mt-1.5 text-[10px] text-muted-foreground">
          {done === 'applied'
            ? t('propose.applied', { defaultValue: 'Applied ✓' })
            : t('propose.dismissed', { defaultValue: 'Dismissed' })}
        </div>
      )}
    </div>
  );
}
