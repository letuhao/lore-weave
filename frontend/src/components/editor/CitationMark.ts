import { Mark, mergeAttributes } from '@tiptap/core';

/**
 * wiki-llm M7a — the stored `citation` mark (emitted by the BE in
 * `ir_to_tiptap`, present in every AI-generated `body_json`). Registering it on
 * the wiki editor means the structured provenance (cite_id / source / chapter /
 * block / score / snippet) ROUND-TRIPS through a human edit — a citation
 * silently dropped on the first save would defeat the audit trail (risk #1a).
 *
 * The attribute KEYS match the BE JSON exactly so the TipTap JSON round-trip
 * preserves them; the per-attribute data-* mapping is only for HTML copy-paste.
 * The rich reader popover lives in `CitationChip`; in the editor the mark renders
 * as a `[n]` chip via the `.citation-mark` class.
 */
const attr = (key: string, html: string) => ({
  default: null as unknown,
  parseHTML: (el: HTMLElement) => el.getAttribute(`data-${html}`),
  renderHTML: (attrs: Record<string, unknown>) =>
    attrs[key] == null ? {} : { [`data-${html}`]: String(attrs[key]) },
});

export const CitationMark = Mark.create({
  name: 'citation',
  inclusive: false,

  addAttributes() {
    return {
      cite_id: attr('cite_id', 'cite-id'),
      n: attr('n', 'n'),
      source_type: attr('source_type', 'source-type'),
      chapter_id: attr('chapter_id', 'chapter-id'),
      block_index: attr('block_index', 'block-index'),
      score: attr('score', 'score'),
      snippet: attr('snippet', 'snippet'),
    };
  },

  parseHTML() {
    return [{ tag: 'span[data-citation]' }];
  },

  renderHTML({ HTMLAttributes }) {
    return [
      'span',
      mergeAttributes(HTMLAttributes, { 'data-citation': '', class: 'citation-mark' }),
      0,
    ];
  },
});
