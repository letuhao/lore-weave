// LOOM Composition (T5.3) — AI-provenance controller.
//
// Owns the editor-facing provenance UI state: whether the unreviewed-AI underlay
// is shown (per-device, localStorage — UI-only, allowed by CLAUDE.md), the live
// count of unreviewed AI spans, and the "mark all reviewed" action. The mark
// itself + click-to-review live in ProvenanceMark.ts; this is the host glue.
import { useCallback, useEffect, useState, type RefObject } from 'react';
import type { TiptapEditorHandle } from '@/components/editor/TiptapEditor';

const VISIBLE_KEY = 'lw-provenance-visible';

function readVisible(): boolean {
  try {
    return localStorage.getItem(VISIBLE_KEY) !== '0'; // default ON (always-on underlay)
  } catch {
    return true;
  }
}

export function useProvenance(editorRef: RefObject<TiptapEditorHandle>, docJson: unknown) {
  const [visible, setVisible] = useState<boolean>(readVisible);
  const [unreviewedCount, setUnreviewedCount] = useState(0);

  // Push the underlay-visibility into the editor (mount + whenever it changes,
  // and re-assert after a doc swap re-creates the view).
  useEffect(() => {
    editorRef.current?.setProvenanceVisible(visible);
  }, [editorRef, visible, docJson]);

  // Recompute the badge whenever the doc mutates (insert AI, review-click, markAll
  // all flow through onUpdate → a new docJson).
  useEffect(() => {
    setUnreviewedCount(editorRef.current?.getUnreviewedProvenanceCount() ?? 0);
  }, [editorRef, docJson]);

  const toggleVisible = useCallback(() => {
    setVisible((v) => {
      const next = !v;
      try { localStorage.setItem(VISIBLE_KEY, next ? '1' : '0'); } catch { /* ignore */ }
      editorRef.current?.setProvenanceVisible(next);
      return next;
    });
  }, [editorRef]);

  const markAllReviewed = useCallback(() => {
    const n = editorRef.current?.markAllProvenanceReviewed() ?? 0;
    setUnreviewedCount(editorRef.current?.getUnreviewedProvenanceCount() ?? 0);
    return n;
  }, [editorRef]);

  return { visible, toggleVisible, unreviewedCount, markAllReviewed };
}
