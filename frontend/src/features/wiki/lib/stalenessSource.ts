// wiki-llm W6b-1 — map a staleness row's source_ref to a "view source" jump URL.
//
// The change-feed records WHICH source changed as source_ref = {source_type,
// source_id, ...} (set by the glossary staleness consumer). This turns that
// reference into a navigable URL so the reader can go look at the current source:
//   - 'entity' (entity_changed / merged) → the glossary tab (no entity-level
//     deep-link route exists yet, so this lands tab-level, not entity-precise)
//   - 'block'  (chapter_regrounded / citation_broken) → the chapter reader
//   - 'kg' / 'recipe' / anything else → null (no single viewable source —
//     a recipe/KG drift isn't a "go look at this text" change)
//
// A true old→new text diff is W6b-2 (capture-forward); this is the universal
// "what/where changed" affordance that works on every existing row.

export function sourceJumpUrl(
  bookId: string,
  sourceRef: Record<string, unknown> | null | undefined,
): string | null {
  if (!bookId || !sourceRef) return null;
  const type = typeof sourceRef.source_type === 'string' ? sourceRef.source_type : '';
  const id = typeof sourceRef.source_id === 'string' ? sourceRef.source_id : '';

  switch (type) {
    case 'entity':
      return `/books/${bookId}/glossary`;
    case 'block':
      return id ? `/books/${bookId}/chapters/${id}/read` : null;
    default:
      return null;
  }
}
