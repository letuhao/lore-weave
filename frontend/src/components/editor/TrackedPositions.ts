// LOOM Composition (WS-C — D-T3.2-SELECTION-RANGE-MAP / D-T3.3-GHOST-POS-MAP) —
// a position-remap plugin: the position analogue of GrammarPlugin's
// `decorations.map(tr.mapping, tr.doc)`. It keeps a set of tracked positions/ranges
// and remaps them through every document change (`tr.mapping`), so a saved insert
// point or selection range stays CORRECT when the doc is edited mid-stream — instead
// of the crude `pos > doc.content.size` bounds check, which silently corrupted on an
// edit BEFORE the range (the range shifts but never exceeds size → wrong-offset insert).
//
// Usage: add `TrackedPositionsExtension` to the editor; call `trackPosition(editor,
// pos)` / `trackRange(editor, from, to)` to get a handle with `.current()` (the live
// mapped value, or null if the position/range was deleted) and `.release()`.
import { Extension } from '@tiptap/core';
import { Plugin, PluginKey } from '@tiptap/pm/state';
import type { Editor } from '@tiptap/react';

type Entry =
  | { kind: 'pos'; assoc: number; pos: number | null }
  | { kind: 'range'; fromAssoc: number; toAssoc: number; from: number | null; to: number | null };

type TrackedState = Map<number, Entry>;

export const trackedPositionsKey = new PluginKey<TrackedState>('lwTrackedPositions');

type Meta =
  | { type: 'add'; id: number; entry: Entry }
  | { type: 'remove'; id: number };

/** The raw PM plugin (exported for unit-testing the mapping against a real
 *  EditorState without a DOM view). The Extension just mounts this. */
export function trackedPositionsPlugin(): Plugin<TrackedState> {
  return new Plugin<TrackedState>({
        key: trackedPositionsKey,
        state: {
          init: () => new Map(),
          apply(tr, prev) {
            const meta = tr.getMeta(trackedPositionsKey) as Meta | undefined;
            let next = prev;
            if (meta?.type === 'add') {
              next = new Map(prev);
              next.set(meta.id, meta.entry);
            } else if (meta?.type === 'remove') {
              next = new Map(prev);
              next.delete(meta.id);
            }
            if (!tr.docChanged || next.size === 0) return next;
            // Remap every tracked entry through the doc change (the core fix).
            const mapped: TrackedState = new Map();
            next.forEach((e, id) => {
              if (e.kind === 'pos') {
                if (e.pos == null) { mapped.set(id, e); return; }
                const r = tr.mapping.mapResult(e.pos, e.assoc);
                mapped.set(id, { ...e, pos: r.deleted ? null : r.pos });
                return;
              }
              if (e.from == null || e.to == null) { mapped.set(id, e); return; }
              const rf = tr.mapping.mapResult(e.from, e.fromAssoc);
              const rt = tr.mapping.mapResult(e.to, e.toAssoc);
              // The range is dead only if BOTH endpoints were deleted (the whole span
              // was removed). A partial inner edit keeps the surviving core.
              if (rf.deleted && rt.deleted) {
                mapped.set(id, { ...e, from: null, to: null });
              } else {
                mapped.set(id, { ...e, from: rf.pos, to: rt.pos });
              }
            });
            return mapped;
          },
        },
      });
}

export const TrackedPositionsExtension = Extension.create({
  name: 'lwTrackedPositions',
  addProseMirrorPlugins() {
    return [trackedPositionsPlugin()];
  },
});

// Module-local id counter — deterministic, unique per session (no Date/random).
let counter = 0;

export type PositionHandle = {
  /** The live mapped position, or null if it was deleted. */
  current(): number | null;
  /** Stop tracking (remove from the plugin state). */
  release(): void;
};

export type RangeHandle = {
  /** The live mapped {from,to}, or null if the range was deleted / collapsed. */
  current(): { from: number; to: number } | null;
  release(): void;
};

function dispatchMeta(editor: Editor, meta: Meta): void {
  // Guard a destroyed editor — a handle.release() in an unmount cleanup can fire
  // after the editor itself was torn down; dispatching then would throw.
  if (editor.isDestroyed) return;
  editor.view.dispatch(editor.view.state.tr.setMeta(trackedPositionsKey, meta));
}

/** Track a single position (e.g. an insert caret). `assoc` -1 keeps it before
 *  content inserted exactly at it, +1 after (default -1). */
export function trackPosition(editor: Editor, pos: number, assoc = -1): PositionHandle {
  const id = ++counter;
  dispatchMeta(editor, { type: 'add', id, entry: { kind: 'pos', assoc, pos } });
  return {
    current() {
      const e = trackedPositionsKey.getState(editor.view.state)?.get(id);
      return e && e.kind === 'pos' ? e.pos : null;
    },
    release() {
      dispatchMeta(editor, { type: 'remove', id });
    },
  };
}

/** Track a range (e.g. a selection to replace). Defaults are CONSERVATIVE
 *  (fromAssoc +1, toAssoc -1) so the range shrinks to its surviving core rather
 *  than absorbing text typed at its edges mid-stream — a replace never eats
 *  newly-authored adjacent prose. Returns null from `.current()` once the range
 *  is deleted or collapses to empty. */
export function trackRange(
  editor: Editor,
  from: number,
  to: number,
  fromAssoc = 1,
  toAssoc = -1,
): RangeHandle {
  const id = ++counter;
  dispatchMeta(editor, { type: 'add', id, entry: { kind: 'range', fromAssoc, toAssoc, from, to } });
  return {
    current() {
      const e = trackedPositionsKey.getState(editor.view.state)?.get(id);
      if (!e || e.kind !== 'range' || e.from == null || e.to == null || e.from >= e.to) return null;
      return { from: e.from, to: e.to };
    },
    release() {
      dispatchMeta(editor, { type: 'remove', id });
    },
  };
}
