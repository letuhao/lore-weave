import { useContext, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Sparkles, Check, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { getEditorTarget } from '../context/editorBridge';
import { buildHunks, reconstruct } from '../utils/proseHunks';
import { useChatStream } from '../providers';
import type { ToolCallRecord } from '../types';
// #16 2.8 — cross-window Apply escape hatch. Non-null ONLY inside Studio's popped-out
// Compose window (StudioPopoutHost provides it); every other surface (ChapterEditorPage's
// chat dock, Studio's docked ComposePanel) never supplies it, so this is strictly additive.
import { PopoutRelayContext } from '@/features/studio/popout/popoutRelayContext';

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
  // #16 2.8 — non-null only inside Studio's popped-out Compose window.
  const popoutRelay = useContext(PopoutRelayContext);

  const args = (record.args ?? {}) as ProposeArgs;
  const text = args.text ?? '';
  const operation = args.operation ?? 'insert_at_cursor';

  // C6 hunk-review — for a rewrite (replace_selection) we snapshot the selected
  // text ONCE at mount (the editor keeps its ProseMirror selection even while the
  // chat input has focus), diff it against the proposal, and offer per-hunk
  // accept/reject. Captured at mount so the diff is stable while the user reviews.
  // null ⇒ no selection / no editor / an insertion → fall back to whole-text Apply.
  const [oldSel] = useState<string | null>(() => {
    if (operation !== 'replace_selection') return null;
    const sel = getEditorTarget()?.handle.getSelection();
    return sel && !sel.empty ? sel.text : null;
  });
  // /review-impl HIGH fix — the `chapterId` prop below is never actually supplied by any
  // caller (AssistantMessage renders `<ProposeEditCard record={tc} />` with no chapterId), so
  // the "never write a proposal into a different document" guard at apply() was dead: on any
  // surface where the editor stays mounted across a chapter switch (Studio's dock — a route
  // navigation would remount the legacy editor page instead, key={bookId} only), a user could
  // switch chapters after a proposal renders and Apply would silently splice chapter A's
  // suggestion into chapter B's document. Self-derive the target chapter from the live editor
  // bridge AT MOUNT (immediately after this card first renders for the suspended tool call —
  // the same instant editor_context/registerEditorTarget agree on "the chapter this proposal
  // is for") so the guard has a real value without requiring prop-threading through the whole
  // shared message-list chain (AssistantMessage/MessageBubble/MessageList serve surfaces with
  // no chapter concept at all). The `chapterId` prop still wins if a caller ever supplies one.
  const [mountChapterId] = useState<string | null>(() => chapterId ?? getEditorTarget()?.chapterId ?? null);
  const model = useMemo(
    () => (oldSel != null ? buildHunks(oldSel, text) : null),
    [oldSel, text],
  );
  const hasHunks = model != null && model.hunks.length > 0;
  // Default: accept every hunk (Apply then behaves exactly like today's whole-text Apply).
  const [accepted, setAccepted] = useState<Set<number>>(
    () => new Set(model ? model.hunks.map((h) => h.id) : []),
  );
  const allAccepted = model != null && accepted.size === model.hunks.length;

  function toggleHunk(id: number) {
    setAccepted((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function apply() {
    if (busy || done) return;
    // Reject-all in the hunk view = nothing to write → treat as Dismiss (resolve
    // the suspended run). Checked BEFORE the editor guards: dismissing needs no
    // editor, so a closed/other chapter must not block it.
    if (hasHunks && accepted.size === 0) {
      await dismiss();
      return;
    }
    const target = getEditorTarget();
    if (!target) {
      // #16 2.8 — inside a popped-out Compose window, getEditorTarget() is ALWAYS null (the
      // module-singleton editorBridge only exists in the window that registered it — the main
      // Studio window's EditorPanel). When PopoutRelayContext is present, relay instead of
      // showing the "no editor" error — the opener's EditorPanel receives it over the
      // per-(book,chapter) BroadcastChannel via usePopoutInsertRelay and applies it through
      // checkpoints.applyProposedEdit, so it still captures a restore point like every other
      // AI-apply path.
      if (popoutRelay) {
        if (operation === 'replace_selection') {
          // A popout has no live editor selection to check against (oldSel is captured via
          // getEditorTarget() at mount too, so it's always null here — hasHunks is always
          // false in a popout) — there is nothing sensible to relay a "replace" onto.
          toast.error(t('propose.popout_no_rewrite', {
            defaultValue: 'Rewrites need to be applied from the docked editor — dock this window first.',
          }));
          return;
        }
        // insert_at_cursor: hasHunks is always false in a popout (no live selection to diff
        // against), so `text` IS the applied text — no hunk-merge branch to run through.
        // #16 2.8 /review-impl HIGH fix — AWAIT the opener's ack instead of assuming the relay
        // landed. The opener may have since navigated to a different chapter (its
        // usePopoutInsertRelay subscription re-keys on chapterId), in which case nothing is
        // listening on this channel and the message vanishes — without this check the card
        // would show "Applied ✓" and tell the LLM the edit succeeded while the document was
        // never touched.
        setBusy(true);
        try {
          const delivered = await popoutRelay.post(text, undefined);
          if (!delivered) {
            toast.error(t('propose.popout_not_delivered', {
              defaultValue: 'Could not confirm the edit reached the docked editor — open the chapter in Studio and try again.',
            }));
            return;
          }
          setDone('applied');
          if (record.runId && record.toolCallId) {
            await submitToolResult(record.runId, record.toolCallId, 'applied', text);
          }
        } finally {
          setBusy(false);
        }
        return;
      }
      toast.error(t('propose.no_editor', { defaultValue: 'Open the chapter to apply this edit.' }));
      return;
    }
    // Chapter-match guard — never write a proposal into a different document.
    if (mountChapterId && target.chapterId !== mountChapterId) {
      toast.error(t('propose.wrong_chapter', { defaultValue: 'This suggestion was for a different chapter.' }));
      return;
    }
    // T5.3 — chat-proposed edits are AI prose; tag them so they carry the
    // unreviewed-AI provenance mark like co-writer insertions.
    const prov = { source: 'ai', status: 'unreviewed' as const, ts: new Date().toISOString() };
    // When reviewing hunks, write the reconstructed merge; accept-all keeps the
    // proposal byte-identical to today (no sentence-normalization of the happy path).
    let applied = text;
    if (hasHunks && !allAccepted && model) {
      // A partial merge re-injects the OLD sentences (for rejected hunks) — that is
      // only correct if the live selection is STILL the span we diffed at mount. If
      // the user moved/shrank it since, abort rather than splice stale text into a
      // different range (buttons stay, the run stays suspended → user can re-ask).
      const live = target.handle.getSelection();
      if (!live || live.empty || live.text.trim() !== (oldSel ?? '').trim()) {
        toast.error(t('propose.selection_changed', { defaultValue: 'Your selection changed — re-select and Apply, or Dismiss.' }));
        return;
      }
      applied = reconstruct(model, accepted);
    }
    // #16 P1 (Lane C — spec 09) — when the registrant supplies a hoist-owned write action
    // (Studio's ManuscriptUnitProvider), call it instead of reaching into the raw handle
    // directly; same underlying Tiptap command either way (legacy has no hoist and omits
    // this field, so its Apply path is byte-identical to before).
    let ok = false;
    if (operation === 'replace_selection') {
      ok = target.applyProposedEdit
        ? target.applyProposedEdit({ operation: 'replace_selection', text: applied, provenance: prov })
        : target.handle.replaceSelection(applied, prov);
      if (!ok) {
        toast.error(t('propose.no_selection', { defaultValue: 'Select the text to replace, then Apply.' }));
        return;
      }
    } else {
      ok = target.applyProposedEdit
        ? target.applyProposedEdit({ operation: 'insert_at_cursor', text: applied, provenance: prov })
        : target.handle.insertAtCursor(applied, prov);
      if (!ok) {
        toast.error(t('propose.apply_failed', { defaultValue: 'Could not apply the edit.' }));
        return;
      }
    }
    setBusy(true);
    setDone('applied');
    try {
      if (record.runId && record.toolCallId) {
        await submitToolResult(record.runId, record.toolCallId, 'applied', applied);
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
      {hasHunks && model ? (
        <div data-testid="propose-hunks" className="max-h-52 space-y-1 overflow-y-auto rounded bg-background/60 p-1.5">
          <div className="mb-0.5 text-[10px] text-muted-foreground">
            {t('propose.hunk_hint', { defaultValue: 'Pick which changes to apply' })}
            {` · ${accepted.size}/${model.hunks.length}`}
          </div>
          {model.segments.map((seg, si) =>
            seg.kind === 'ctx' ? (
              <div key={`c${si}`} className="truncate px-0.5 text-[10px] text-muted-foreground/60">
                {seg.unit.text}
              </div>
            ) : (
              (() => {
                const h = model.hunks[seg.id];
                const on = accepted.has(seg.id);
                return (
                  <label
                    key={`h${seg.id}`}
                    data-testid={`propose-hunk-${seg.id}`}
                    data-accepted={on}
                    className="flex cursor-pointer items-start gap-1.5 rounded px-0.5 py-0.5 hover:bg-accent/5"
                  >
                    <input
                      type="checkbox"
                      checked={on}
                      onChange={() => toggleHunk(seg.id)}
                      disabled={busy}
                      className="mt-0.5 accent-[var(--accent)]"
                      aria-label={t('propose.hunk_toggle', { defaultValue: 'Accept this change' })}
                    />
                    <div className="min-w-0 flex-1 space-y-0.5 text-[11px]">
                      {h.oldUnits.map((u, k) => (
                        <div
                          key={`o${k}`}
                          className={cn('whitespace-pre-wrap', on ? 'text-foreground/40 line-through' : 'text-foreground/80')}
                        >
                          {u.text}
                        </div>
                      ))}
                      {h.newUnits.map((u, k) => (
                        <div
                          key={`n${k}`}
                          className={cn('whitespace-pre-wrap', on ? 'text-emerald-400' : 'text-emerald-400/40 line-through')}
                        >
                          {u.text}
                        </div>
                      ))}
                    </div>
                  </label>
                );
              })()
            ),
          )}
        </div>
      ) : (
        <pre className="max-h-40 overflow-y-auto whitespace-pre-wrap rounded bg-background/60 p-1.5 font-sans text-[11px] text-foreground/90">
          {text}
        </pre>
      )}
      {done === null ? (
        <div className="mt-1.5 flex gap-1.5">
          <button
            type="button"
            onClick={apply}
            disabled={busy}
            className="inline-flex items-center gap-1 rounded-sm bg-accent px-2 py-0.5 text-[11px] font-medium text-accent-foreground hover:brightness-110 disabled:opacity-50"
          >
            <Check className="h-3 w-3" />
            {!hasHunks || allAccepted
              ? t('propose.apply', { defaultValue: 'Apply' })
              : accepted.size === 0
                ? t('propose.keep_original', { defaultValue: 'Keep original' })
                : t('propose.apply_n', { defaultValue: 'Apply {{count}}', count: accepted.size })}
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
