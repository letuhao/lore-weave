// LOOM Composition (T5.3) — AI-provenance highlight.
//
// A stored Tiptap `provenance` mark that records which prose was AI-written vs
// human-authored. It rides in the chapter `body_json` (book-service stores the
// draft body verbatim as json.RawMessage — no allowlist/strip — so the mark
// ROUND-TRIPS through save→reload, the audit trail's whole point).
//
// Unreviewed AI spans show a faint underlay (styled `.provenance-unreviewed` in
// index.css); the author clicks one to mark it reviewed (the mark STAYS, status
// flips, the underlay fades — mirrors CitationMark's "keep the provenance"
// intent). Split-on-edit is deferred: typing INSIDE a span keeps the mark.
import { Mark, mergeAttributes, getMarkRange } from '@tiptap/core';
import { Plugin, PluginKey } from '@tiptap/pm/state';

export const provenancePluginKey = new PluginKey('provenance');

export type ProvenanceStatus = 'unreviewed' | 'reviewed';
export type ProvenanceAttrs = {
  source?: string; // 'ai' (default) — room for 'import' etc. later
  status?: ProvenanceStatus;
  model?: string | null; // the model that wrote it (hover tag)
  ts?: string | null; // ISO timestamp
};

// Attribute keys match the JSON exactly so the TipTap round-trip preserves them;
// the per-attribute data-* mapping is for the CSS underlay + the hover tag.
const attr = (key: string, html: string, def: unknown = null) => ({
  default: def,
  parseHTML: (el: HTMLElement) => el.getAttribute(`data-${html}`),
  renderHTML: (attrs: Record<string, unknown>) =>
    attrs[key] == null ? {} : { [`data-${html}`]: String(attrs[key]) },
});

export const ProvenanceMark = Mark.create({
  name: 'provenance',
  inclusive: false, // typing at a span boundary does NOT extend the AI mark

  addAttributes() {
    return {
      source: attr('source', 'source', 'ai'),
      status: attr('status', 'status', 'unreviewed'),
      model: attr('model', 'model'),
      ts: attr('ts', 'ts'),
    };
  },

  parseHTML() {
    return [{ tag: 'span[data-provenance]' }];
  },

  renderHTML({ HTMLAttributes }) {
    const status = (HTMLAttributes['data-status'] as string) || 'unreviewed';
    return [
      'span',
      mergeAttributes(HTMLAttributes, {
        'data-provenance': '',
        class: `provenance-mark provenance-${status}`,
      }),
      0,
    ];
  },

  addProseMirrorPlugins() {
    const editor = this.editor;
    return [
      new Plugin({
        key: provenancePluginKey,
        props: {
          // Click an unreviewed AI span → review it (consumes the click). A click
          // outside any span, or on an already-reviewed one, falls through to the
          // normal caret placement.
          handleClick: (_view, pos) => reviewProvenanceAt(editor, pos),
        },
      }),
    ];
  },
});

// --- helpers (also the test surface for the click/markAll logic) -------------

/** Wrap [from,to) as a provenance span (defaults: source=ai, status=unreviewed). */
export function applyProvenanceOver(editor: any, from: number, to: number, attrs: ProvenanceAttrs = {}) {
  if (!editor || from >= to) return;
  const type = editor.schema.marks.provenance;
  if (!type) return; // editor without the mark registered (e.g. a non-composition target)
  const mark = type.create({ source: 'ai', status: 'unreviewed', model: null, ts: null, ...attrs });
  const tr = editor.state.tr;
  tr.addMark(from, to, mark);
  editor.view.dispatch(tr);
}

function markAt(editor: any, pos: number) {
  const type = editor.schema.marks.provenance;
  if (!type) return null; // mark not in this editor's schema → nothing to review
  const $pos = editor.state.doc.resolve(pos);
  const range = getMarkRange($pos, type);
  if (!range) return null;
  let mark: any = null;
  editor.state.doc.nodesBetween(range.from, range.to, (node: any) => {
    if (mark) return false;
    const m = node.marks?.find((mk: any) => mk.type === type);
    if (m) mark = m;
  });
  return mark ? { range, mark } : null;
}

/** Flip the unreviewed provenance span covering `pos` to reviewed. Returns true
 *  iff a flip happened (used as the plugin's handleClick consume signal). */
export function reviewProvenanceAt(editor: any, pos: number): boolean {
  const hit = markAt(editor, pos);
  if (!hit || hit.mark.attrs.status === 'reviewed') return false;
  const type = editor.schema.marks.provenance;
  const tr = editor.state.tr;
  tr.removeMark(hit.range.from, hit.range.to, type);
  tr.addMark(hit.range.from, hit.range.to, type.create({ ...hit.mark.attrs, status: 'reviewed' }));
  editor.view.dispatch(tr);
  return true;
}

function unreviewedRanges(editor: any): Array<{ from: number; to: number; attrs: any }> {
  const type = editor.schema.marks.provenance;
  const out: Array<{ from: number; to: number; attrs: any }> = [];
  editor.state.doc.descendants((node: any, pos: number) => {
    if (!node.isText) return;
    const m = node.marks?.find((mk: any) => mk.type === type && mk.attrs.status !== 'reviewed');
    if (m) out.push({ from: pos, to: pos + node.nodeSize, attrs: m.attrs });
  });
  return out;
}

/** Number of unreviewed AI spans currently in the doc (for the toolbar badge). */
export function countUnreviewedProvenance(editor: any): number {
  if (!editor) return 0;
  return unreviewedRanges(editor).length;
}

/** Flip every unreviewed AI span to reviewed in one transaction. Returns the count. */
export function markAllProvenanceReviewed(editor: any): number {
  if (!editor) return 0;
  const ranges = unreviewedRanges(editor);
  if (ranges.length === 0) return 0;
  const type = editor.schema.marks.provenance;
  const tr = editor.state.tr;
  for (const r of ranges) {
    tr.removeMark(r.from, r.to, type);
    tr.addMark(r.from, r.to, type.create({ ...r.attrs, status: 'reviewed' }));
  }
  editor.view.dispatch(tr);
  return ranges.length;
}

/** Show/hide the unreviewed-AI underlay (toolbar eye toggle). Default: visible. */
export function setProvenanceVisible(editor: any, visible: boolean) {
  if (!editor?.view?.dom) return;
  editor.view.dom.classList.toggle('provenance-underlay-off', !visible);
}
