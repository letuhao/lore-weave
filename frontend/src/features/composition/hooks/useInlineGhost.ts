// LOOM Composition (T3.3) — inline-ghost controller. Moves the cowrite stream's
// ghost from the side panel INTO the manuscript at the cursor: ✦ Continue streams
// /generate {operation:'continue'} grounded on the active scene, rendered as a
// position-fixed overlay at the caret. Accept commits it (+ advisory critique),
// Edit inserts it editable, Discard drops it, Regenerate re-streams. Reuses
// useCompositionStream (abort-on-restart) + useCritique. No new BE.
import { useCallback, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import type { Editor } from '@tiptap/react';
import { useCompositionStream } from './useCompositionStream';
import { useCritique } from './useCritique';

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
  const [anchor, setAnchor] = useState<GhostAnchor | null>(null);

  const canContinue = !!editor && !!opts.projectId && !!opts.sceneId && !!opts.modelRef;

  // Caret coords (viewport) for the fixed overlay; below the cursor line.
  const coordsAt = useCallback((pos: number) => {
    if (!editor) return { top: 0, left: 0 };
    const c = editor.view.coordsAtPos(pos);
    return { top: c.bottom, left: c.left };
  }, [editor]);

  const reposition = useCallback(() => {
    setAnchor((a) => (a ? { ...a, coords: coordsAt(a.pos) } : a));
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
    setAnchor({ pos, coords: coordsAt(pos) });
    startAt(pos);
  }, [canContinue, editor, coordsAt, startAt]);

  const close = useCallback(() => { stream.clearGhost(); setAnchor(null); }, [stream]);
  const discard = useCallback(() => { stream.stop(); close(); }, [stream, close]);

  // runCritique=false is the "Edit" path: the prose lands in the doc (editable) but
  // we skip the advisory critique (it's a one-shot judge of an accepted passage).
  const commit = useCallback((runCritique: boolean) => {
    if (!editor || !anchor || !stream.ghost) return;
    // The editor stays editable during the ghost; if the doc shrank the saved pos
    // can go stale → bounds-check before inserting (D-T3.3-GHOST-POS-MAP for full
    // position mapping).
    if (anchor.pos > editor.state.doc.content.size) {
      toast.error(t('inline.stale', { defaultValue: 'The cursor moved — try again.' }));
      close();
      return;
    }
    editor.chain().focus().insertContentAt(anchor.pos, stream.ghost).run();
    if (runCritique && stream.jobId) critique.mutate({ jobId: stream.jobId, passage: stream.ghost });
    close();
  }, [editor, anchor, stream.ghost, stream.jobId, critique, close, t]);

  const regenerate = useCallback(() => {
    if (!anchor) return;
    stream.clearGhost();
    startAt(anchor.pos);
  }, [anchor, stream, startAt]);

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
