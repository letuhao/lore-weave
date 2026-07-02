// LOOM Composition (T3.2) — Selection Tools. A Tiptap floating toolbar over a prose
// selection offering Rewrite / Expand / Describe. Choosing one streams a grounded,
// voice-consistent replacement (reuses useCompositionStream in selection mode) shown
// as a ghost; Accept replaces the saved range, Discard reverts. Self-contained model
// picker (PO). Grounding couples to the compose panel's active scene (sceneContext).
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { BubbleMenu } from '@tiptap/react/menus';
import type { Editor } from '@tiptap/react';
import { ModelPicker, useUserModels } from '@/components/model-picker';
import { trackRange, type RangeHandle } from '../../../components/editor/TrackedPositions';
import { useCompositionStream } from '../hooks/useCompositionStream';
import type { SelectionOperation } from '../types';

export const SELECTION_MAX_CHARS = 8000;
const OPS: SelectionOperation[] = ['rewrite', 'expand', 'describe'];

export function SelectionToolbar({
  editor, projectId, sceneContext, token,
}: {
  editor: Editor;
  projectId: string;
  sceneContext: string | null;
  token: string | null;
}) {
  const { t } = useTranslation('composition');
  const stream = useCompositionStream(token);
  const [modelRef, setModelRef] = useState('');
  const [instruction, setInstruction] = useState('');
  // The range captured when the op ran — Accept replaces THIS, not the live
  // selection. WS-C: a TRACKED range (PM remaps it through any edit made while the
  // op streams) so Accept targets the correct span even after an edit BEFORE it —
  // the old saved {from,to} + size-check silently inserted at the wrong offset.
  const savedRange = useRef<RangeHandle | null>(null);
  // An op is "active" from click until Accept/Discard — keeps the bubble open even
  // when the streamed ghost has collapsed the visible selection.
  const [active, setActive] = useState(false);

  // Release the tracked range if the toolbar unmounts mid-op (without Accept/Discard)
  // so a stale entry doesn't linger in the shared editor's plugin state.
  useEffect(() => () => { savedRange.current?.release(); savedRange.current = null; }, []);

  // W5 — the shared user-models fetch (active-only, capability=chat; dedupes with
  // every other chat picker in the view via the module cache).
  const models = useUserModels({ capability: 'chat' });
  const modelList = models.models ?? [];
  const effectiveModel = modelRef || modelList[0]?.user_model_id || '';
  const selectedModel = modelList.find((m) => m.user_model_id === effectiveModel);

  const selText = () => {
    const { from, to } = editor.state.selection;
    return editor.state.doc.textBetween(from, to, ' ');
  };
  const tooLong = selText().length > SELECTION_MAX_CHARS;

  const run = (op: SelectionOperation) => {
    const { from, to } = editor.state.selection;
    const text = editor.state.doc.textBetween(from, to, ' ');
    if (!text.trim() || text.length > SELECTION_MAX_CHARS || !effectiveModel) return;
    savedRange.current?.release();
    savedRange.current = trackRange(editor, from, to);
    setActive(true);
    void stream.start({
      projectId,
      selection: text,
      operation: op,
      sceneContext,
      modelSource: 'user_model',
      modelRef: effectiveModel,
      guide: instruction.trim(),
      modelKind: selectedModel?.provider_kind,
      modelName: selectedModel?.provider_model_name,
    });
  };

  const reset = () => { setActive(false); stream.clearGhost(); savedRange.current?.release(); savedRange.current = null; };
  const discard = () => { stream.stop(); reset(); };
  const accept = () => {
    const handle = savedRange.current;
    if (!handle || !stream.ghost) return;
    // WS-C: the tracked range is remapped through every mid-stream edit; .current()
    // returns null only if the span was deleted/collapsed — the PRECISE stale signal
    // (replaces the crude `to > doc.size` check that missed edits before the range).
    const range = handle.current();
    if (!range) {
      toast.error(t('sel.stale', { defaultValue: 'The selection changed — try again.' }));
      reset();
      return;
    }
    editor.chain().focus().deleteRange(range).insertContentAt(range.from, stream.ghost).run();
    reset();
  };

  // Keep the menu open while an op is active (ghost pending), else only on a
  // non-empty selection within the cap.
  const shouldShow = ({ editor: ed }: { editor: Editor }) => {
    if (active) return true;
    return !ed.state.selection.empty;
  };

  return (
    <BubbleMenu editor={editor} shouldShow={shouldShow} data-testid="selection-bubble">
      <div data-testid="selection-toolbar" className="flex max-w-[22rem] flex-col gap-1.5 rounded-md border bg-popover p-2 text-[11px] shadow-md">
        {active ? (
          <>
            <div data-testid="selection-ghost" className="max-h-40 overflow-y-auto whitespace-pre-wrap rounded bg-muted/40 p-1.5 text-foreground">
              {stream.ghost || (stream.streaming ? t('sel.streaming', { defaultValue: 'Generating…' }) : '')}
              {stream.error && <span className="text-rose-600"> {stream.error}</span>}
            </div>
            <div className="flex items-center gap-1.5">
              {stream.streaming ? (
                <button type="button" data-testid="selection-stop" className="rounded bg-rose-600 px-2 py-0.5 text-white" onClick={discard}>
                  {t('sel.stop', { defaultValue: 'Stop' })}
                </button>
              ) : (
                <button type="button" data-testid="selection-accept" className="rounded bg-emerald-600 px-2 py-0.5 text-white disabled:opacity-50" disabled={!stream.ghost} onClick={accept}>
                  {t('sel.accept', { defaultValue: 'Accept' })}
                </button>
              )}
              <button type="button" data-testid="selection-discard" className="rounded border px-2 py-0.5 text-muted-foreground" onClick={discard}>
                {t('sel.discard', { defaultValue: 'Discard' })}
              </button>
            </div>
          </>
        ) : tooLong ? (
          <span data-testid="selection-too-long" className="text-amber-600">
            {t('sel.too_long', { defaultValue: 'Selection too long for AI tools.' })}
          </span>
        ) : (
          <>
            <div className="flex items-center gap-1.5">
              {/* W5 — shared ModelPicker (compact) replaces the bespoke <select>. */}
              <div data-testid="selection-model" className="min-w-0 flex-1">
                <ModelPicker
                  capability="chat"
                  compact
                  value={effectiveModel || null}
                  onChange={(id) => setModelRef(id ?? '')}
                  ariaLabel={t('sel.model', { defaultValue: 'Model' })}
                  placeholder={t('sel.no_model', { defaultValue: 'No model' })}
                />
              </div>
            </div>
            <input
              data-testid="selection-instruction"
              aria-label={t('sel.instruction', { defaultValue: 'Optional instruction' })}
              placeholder={t('sel.instruction', { defaultValue: 'e.g. terser…' })}
              className="rounded border bg-background px-1 py-0.5"
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
            />
            <div className="flex items-center gap-1.5">
              {OPS.map((op) => (
                <button
                  key={op}
                  type="button"
                  data-testid={`selection-${op}`}
                  className="rounded border px-2 py-0.5 hover:border-primary hover:text-primary disabled:opacity-40"
                  disabled={!effectiveModel}
                  onClick={() => run(op)}
                >
                  ✦ {t(`sel.${op}`, { defaultValue: op })}
                </button>
              ))}
            </div>
          </>
        )}
      </div>
    </BubbleMenu>
  );
}
