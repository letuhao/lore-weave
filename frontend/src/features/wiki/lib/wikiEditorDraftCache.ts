// 15_wiki_panels.md /review-impl — DOCK-10 gap: `wiki-editor`'s body/dirty state lived entirely
// inside the panel's own React tree, so closing the dock tab (drag-to-close, middle-click, the
// tab's own X button) while dirty silently discarded the draft on remount — a failure mode the
// G7 params-retargeting guard never covered (that guard only handles staying open and switching
// articles, not closing outright). This is a NEW risk the panel migration introduces: the classic
// page has no "close this tab" concept at all. D4 states the underlying cause plainly: "dockview
// unmounts a closed panel."
//
// Manuscript chapters solve this with a real Tier-4 `ManuscriptUnitProvider` mounted above
// dockview (StudioFrame.tsx) — deliberately more machinery than Wiki needs: `wiki-editor` is a
// singleton (only ONE draft can ever be in flight at a time), so a module-level cache outside
// the React tree is enough — same technique as the binding-bridge in
// `features/glossary/documents/entityDocument.ts`: a plain variable survives component
// unmount/remount because it isn't React state.
interface WikiEditorDraft {
  articleId: string;
  body: unknown;
}

let draft: WikiEditorDraft | null = null;

/** Returns the cached draft ONLY if it matches this exact article — a stale draft for a
 *  DIFFERENT article is never silently applied to the wrong resource. */
export function getWikiEditorDraft(articleId: string): unknown | null {
  return draft && draft.articleId === articleId ? draft.body : null;
}

/** Called on every editor keystroke so the cache always holds the LATEST content, not just
 *  the content as of some earlier checkpoint. */
export function setWikiEditorDraft(articleId: string, body: unknown): void {
  draft = { articleId, body };
}

/** Called on successful save, or when the user explicitly discards (Back-while-dirty confirm,
 *  the G7 discard-and-switch confirm) — a clean article has nothing left to restore. */
export function clearWikiEditorDraft(): void {
  draft = null;
}

/** Test-only: reset module state between test files. */
export function _resetWikiEditorDraftCache(): void {
  draft = null;
}
