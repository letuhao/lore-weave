// LOOM Composition (T3.3) — inline-ghost controller. Moves the cowrite stream's
// ghost from the side panel INTO the manuscript at the cursor: ✦ Continue streams
// /generate {operation:'continue'} grounded on the active scene, rendered as a
// position-fixed overlay at the caret. Accept commits it (+ advisory critique),
// Edit inserts it editable, Discard drops it, Regenerate re-streams. Reuses
// useCompositionStream (abort-on-restart) + useCritique. No new BE.
import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import type { Editor } from '@tiptap/react';
import { trackPosition, type PositionHandle } from '../../../components/editor/TrackedPositions';
import { useCompositionStream } from './useCompositionStream';
import { useCritique } from './useCritique';
import { useCorrection } from './useAutoGenerate';
import type { CorrectionBody } from '../types';

export type GhostAnchor = { pos: number; coords: { top: number; left: number } };

export function useInlineGhost(
  editor: Editor | null,
  opts: {
    projectId: string | null;
    sceneId: string | null;
    modelRef: string | null;
    modelKind?: string;
    modelName?: string;
    token: string | null;
  },
) {
  const { t } = useTranslation('composition');
  const stream = useCompositionStream(opts.token);
  const { critique } = useCritique(opts.token);
  const correction = useCorrection(opts.token);
  const [anchor, setAnchor] = useState<GhostAnchor | null>(null);
  // WS-C: the insert caret is a TRACKED position — PM remaps it through any edit the
  // author makes while the ghost streams, so commit inserts at the RIGHT spot (and
  // detects a true deletion) instead of the crude `pos > doc.size` bounds check.
  const posHandle = useRef<PositionHandle | null>(null);

  const canContinue = !!editor && !!opts.projectId && !!opts.sceneId && !!opts.modelRef;

  // Caret coords (viewport) for the fixed overlay; below the cursor line.
  const coordsAt = useCallback((pos: number) => {
    if (!editor) return { top: 0, left: 0 };
    const c = editor.view.coordsAtPos(pos);
    return { top: c.bottom, left: c.left };
  }, [editor]);

  const reposition = useCallback(() => {
    // Follow the tracked position (if it moved under a concurrent edit) when
    // recomputing the overlay coords; fall back to the stored pos.
    setAnchor((a) => {
      if (!a) return a;
      const pos = posHandle.current?.current() ?? a.pos;
      return { pos, coords: coordsAt(pos) };
    });
  }, [coordsAt]);

  const startAt = useCallback((pos: number) => {
    void stream.start({
      projectId: opts.projectId!,
      outlineNodeId: opts.sceneId!,
      operation: 'continue',
      modelSource: 'user_model',
      modelRef: opts.modelRef!,
      modelKind: opts.modelKind,
      modelName: opts.modelName,
    });
  }, [stream, opts.projectId, opts.sceneId, opts.modelRef, opts.modelKind, opts.modelName]);

  const continueDraft = useCallback(() => {
    if (!canContinue || !editor) return;
    const pos = editor.state.selection.from;
    posHandle.current?.release();
    posHandle.current = trackPosition(editor, pos);
    setAnchor({ pos, coords: coordsAt(pos) });
    startAt(pos);
  }, [canContinue, editor, coordsAt, startAt]);

  const close = useCallback(() => {
    stream.clearGhost();
    posHandle.current?.release();
    posHandle.current = null;
    setAnchor(null);
  }, [stream]);

  // S1 correction-capture seam (spec §0 flywheel) — the inline "Continue from cursor" ghost is the
  // studio Editor's own draft loop; Discard/Regenerate are genuine dissatisfaction signals, so
  // capture them (composition.generation_corrected → learning-service), the SAME rationale as
  // ComposeView's cowrite gate. Accept/Edit are NOT captured (accept-as-is is not a correction, and
  // the streamed ghost is not editable pre-accept — H2 self-reinforcement guard). Fire-and-forget:
  // never blocks the UI, only fires when a real generation job exists.
  const capture = useCallback((body: CorrectionBody) => {
    if (stream.jobId) correction.mutate({ jobId: stream.jobId, body });
  }, [correction, stream.jobId]);

  const discard = useCallback(() => { capture({ kind: 'reject' }); stream.stop(); close(); }, [capture, stream, close]);

  // runCritique=false is the "Edit" path: the prose lands in the doc (editable) but
  // we skip the advisory critique (it's a one-shot judge of an accepted passage).
  const commit = useCallback((runCritique: boolean) => {
    if (!editor || !anchor || !stream.ghost) return;
    // WS-C: the editor stays editable during the ghost; the TRACKED position is
    // remapped through any edit, so we insert at its live spot. .current() is null
    // only if the caret's location was actually deleted → precise stale signal.
    const pos = posHandle.current?.current() ?? anchor.pos;
    if (pos == null || pos > editor.state.doc.content.size) {
      toast.error(t('inline.stale', { defaultValue: 'The cursor moved — try again.' }));
      close();
      return;
    }
    editor.chain().focus().insertContentAt(pos, stream.ghost).run();
    if (runCritique && stream.jobId) critique.mutate({ jobId: stream.jobId, passage: stream.ghost });
    close();
  }, [editor, anchor, stream.ghost, stream.jobId, critique, close, t]);

  const regenerate = useCallback(() => {
    if (!anchor) return;
    capture({ kind: 'regenerate' }); // capture BEFORE re-stream — startAt mints a new jobId
    stream.clearGhost();
    startAt(posHandle.current?.current() ?? anchor.pos);
  }, [anchor, capture, stream, startAt]);

  // Release the tracked caret if the hook unmounts mid-ghost (without a commit/
  // discard) so a stale entry doesn't linger in the shared editor's plugin state.
  useEffect(() => () => { posHandle.current?.release(); posHandle.current = null; }, []);

  return {
    anchor,
    ghost: stream.ghost,
    streaming: stream.streaming,
    error: stream.error,
    canContinue,
    continueDraft,
    accept: () => commit(true),
    edit: () => commit(false),
    discard,
    regenerate,
    reposition,
  };
}
