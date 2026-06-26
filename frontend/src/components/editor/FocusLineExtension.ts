// LOOM Composition (T5.1) — FocusLine extension.
//
// Decorates the top-level block containing the selection head with a `focusline`
// class, via a ProseMirror node Decoration. This is the PM-native way to mark a
// node: directly mutating `classList` on a `<p>` is wrong because ProseMirror owns
// and reconciles that DOM (it strips foreign classes on re-render). The decoration
// updates automatically on every selection/doc change.
//
// Always on (cheap — one decoration). It's harmless outside focus mode: the
// `.focusline` class only has a visible effect under `.lw-focus` (see index.css),
// so the host doesn't need to toggle this extension.
import { Extension } from '@tiptap/core';
import { Plugin } from '@tiptap/pm/state';
import { Decoration, DecorationSet } from '@tiptap/pm/view';

export const FocusLineExtension = Extension.create({
  name: 'focusLine',

  addProseMirrorPlugins() {
    return [
      new Plugin({
        props: {
          decorations(state) {
            const { $from, $to } = state.selection;
            // depth-1 ancestor = the top-level block (paragraph/heading/…)
            const node = $from.depth >= 1 ? $from.node(1) : null;
            // only mark a single block (collapsed caret / within one block)
            if (!node || $from.before(1) !== $to.before(1)) return DecorationSet.empty;
            const start = $from.before(1);
            return DecorationSet.create(state.doc, [
              Decoration.node(start, start + node.nodeSize, { class: 'focusline' }),
            ]);
          },
        },
      }),
    ];
  },
});
