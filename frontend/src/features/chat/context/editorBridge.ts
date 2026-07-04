// ARCH-1 C6 — editor write-back bridge.
//
// The editor AI panel <Chat> and the Tiptap editor live in different parts of
// the tree (the chat panel doesn't receive the editor ref). When the agent
// proposes an edit and the user clicks Apply, the chat needs to (a) reach the
// editor's imperative handle and (b) confirm the proposal targets the chapter
// that's actually open. A tiny module-singleton registry bridges them —
// mirroring the existing setImageUploadContext / setOnOpenHistory pattern in
// the editor, but exposing a getter so Apply can call a method and read its
// boolean result (a DOM CustomEvent is fire-and-forget; we need the result).
import type { RefObject } from 'react';
import type { TiptapEditorHandle } from '@/components/editor/TiptapEditor';
import type { ProvenanceAttrs } from '@/components/editor/ProvenanceMark';

/** #16 P1 (Lane C — spec 09) — an optional hoist-owned write action. When a registrant supplies
 *  this (the Studio EditorPanel does, via ManuscriptUnitProvider.applyProposedEdit), the chat's
 *  Apply path calls it INSTEAD of reaching into the raw Tiptap handle directly — the actual write
 *  is unchanged (same underlying Tiptap command), but it goes through the Tier-4 hoist's own named
 *  action so future hoist-level bookkeeping (Checkpoints) has one chokepoint. The legacy
 *  ChapterEditorPage has no Tier-4 hoist and omits this field — its Apply path is byte-identical
 *  to before (calls target.handle.* directly). */
export type ApplyProposedEdit = (params: {
  operation: 'insert_at_cursor' | 'replace_selection';
  text: string;
  provenance?: ProvenanceAttrs;
}) => boolean;

interface RegisteredTarget {
  bookId: string;
  chapterId: string;
  handleRef: RefObject<TiptapEditorHandle | null>;
  applyProposedEdit?: ApplyProposedEdit;
}

export interface EditorTarget {
  bookId: string;
  chapterId: string;
  handle: TiptapEditorHandle;
  applyProposedEdit?: ApplyProposedEdit;
}

let _target: RegisteredTarget | null = null;

/** The editor page registers the currently-open chapter + its Tiptap handle
 *  ref. We store the REF (not the current value) so the handle is read live at
 *  Apply time — the editor may mount after registration. Call with null on
 *  unmount/chapter change to clear. */
export function registerEditorTarget(target: RegisteredTarget | null): void {
  _target = target;
}

/** The chat Apply handler reads the live target, or null if no chapter is open
 *  or the editor handle isn't mounted yet. */
export function getEditorTarget(): EditorTarget | null {
  if (!_target) return null;
  const handle = _target.handleRef.current;
  if (!handle) return null;
  return {
    bookId: _target.bookId, chapterId: _target.chapterId, handle,
    applyProposedEdit: _target.applyProposedEdit,
  };
}
