// Render the author's ERROR BLOCKS as inline decorations (atom-edit Phase D).
//
// Without this the feature is half-visible: the author marks a passage, the co-writer can read it
// over MCP, and the author can never see it again. This is the same failure this track already
// caught once — four editors that passed 1596 unit tests with no door to open them.
//
// A DECORATION, not a stored mark. The block lives in Postgres, not in the document: it is an
// annotation ABOUT the prose, not part of it. Storing it as a Tiptap mark would put it in the
// chapter body, where it would be persisted, exported, published, and re-flattened into the very
// text the offsets are measured against. Decorations are a pure view layer — the document is
// byte-identical with and without them.
import { Extension } from '@tiptap/core';
import { Plugin, PluginKey } from '@tiptap/pm/state';
import { Decoration, DecorationSet } from '@tiptap/pm/view';

export const errorBlockPluginKey = new PluginKey('errorBlockMarks');

export interface ErrorBlockDeco {
  id: string;
  from: number;
  to: number;
  kind: string;
  note: string;
  status: string;
}

/** Push a new set of marks into the editor. Positions are PM coordinates, already resolved and
 *  VERIFIED against the quote by `resolveBlockRange` — this plugin trusts them and only draws. */
export function setErrorBlockDecorations(
  view: { state: unknown; dispatch: (tr: unknown) => void },
  blocks: ErrorBlockDeco[],
): void {
  const state = view.state as { tr: { setMeta: (k: unknown, v: unknown) => unknown } };
  view.dispatch(state.tr.setMeta(errorBlockPluginKey, { blocks }));
}

function build(doc: unknown, blocks: ErrorBlockDeco[]): DecorationSet {
  const decos = blocks
    // A zero-width or inverted range would throw inside DecorationSet.create; drop it rather
    // than take the editor down over a stale row.
    .filter((b) => b.to > b.from)
    .map((b) =>
      Decoration.inline(b.from, b.to, {
        class: `lw-error-block lw-error-block--${b.status}`,
        'data-error-block-id': b.id,
        // The note rides on the DOM node so a hover shows WHY the passage was marked without
        // another round-trip. It is the author's own words — the reason the mark exists.
        title: b.note,
        'data-error-block-kind': b.kind,
      }),
    );
  return DecorationSet.create(doc as never, decos);
}

export const ErrorBlockExtension = Extension.create({
  name: 'errorBlockMarks',

  addProseMirrorPlugins() {
    return [
      new Plugin({
        key: errorBlockPluginKey,
        state: {
          init: () => DecorationSet.empty,
          apply(tr, prev: DecorationSet) {
            const meta = tr.getMeta(errorBlockPluginKey) as { blocks?: ErrorBlockDeco[] } | undefined;
            if (meta?.blocks) return build(tr.doc, meta.blocks);
            // Remap through edits so a highlight follows its sentence while the author types,
            // instead of sitting at a stale offset until the next refetch.
            return tr.docChanged ? prev.map(tr.mapping, tr.doc) : prev;
          },
        },
        props: {
          decorations(state) {
            return errorBlockPluginKey.getState(state) as DecorationSet | undefined;
          },
        },
      }),
    ];
  },
});
