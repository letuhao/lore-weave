// LOOM Composition (T5.2) — in-prose mention heatmap.
//
// Tints occurrences of an entity's name in the manuscript by its mention DENSITY
// band (0..4) so the writer SEES which characters dominate the prose. Same
// word-boundary / longest-first / no-overlap matching as GlossaryPlugin, but the
// decoration class encodes the band (`heat-band-N`, styled in index.css). Inert
// until enabled — the host toggles it via setHeatmapEnabled.
import { Extension } from '@tiptap/core';
import { Plugin, PluginKey } from '@tiptap/pm/state';
import { Decoration, DecorationSet } from '@tiptap/pm/view';

export const heatmapPluginKey = new PluginKey('heatmap');

export type HeatTerm = { name: string; band: number };
type SortedTerm = HeatTerm & { nameLower: string };

type HeatmapPluginState = {
  terms: HeatTerm[];
  sorted: SortedTerm[];
  enabled: boolean;
  decorations: DecorationSet;
};

const BOUNDARY = /[\s.,;:!?()[\]{}"""''—–\-/]/;

function sortTerms(terms: HeatTerm[]): SortedTerm[] {
  return [...terms]
    .filter((tm) => tm.name && tm.name.length >= 2)
    .sort((a, b) => b.name.length - a.name.length) // longest first → prefer full-name matches
    .map((tm) => ({ ...tm, nameLower: tm.name.toLowerCase() }));
}

function buildDecorations(doc: any, sorted: SortedTerm[]): DecorationSet {
  if (sorted.length === 0) return DecorationSet.empty;
  const decos: Decoration[] = [];
  doc.descendants((node: any, pos: number) => {
    if (!node.isText || !node.text) return;
    const text = node.text as string;
    const textLower = text.toLowerCase();
    const occupied = new Set<number>();
    for (const term of sorted) {
      const len = term.name.length;
      let from = 0;
      while (from < text.length) {
        const idx = textLower.indexOf(term.nameLower, from);
        if (idx === -1) break;
        const before = idx > 0 ? text[idx - 1] : ' ';
        const after = idx + len < text.length ? text[idx + len] : ' ';
        const ok = (BOUNDARY.test(before) || idx === 0) && (BOUNDARY.test(after) || idx + len === text.length);
        if (ok) {
          let overlaps = false;
          for (let i = idx; i < idx + len; i++) if (occupied.has(i)) { overlaps = true; break; }
          if (!overlaps) {
            for (let i = idx; i < idx + len; i++) occupied.add(i);
            decos.push(Decoration.inline(pos + idx, pos + idx + len, {
              class: `heat-band heat-band-${term.band}`,
              'data-heat-band': String(term.band),
            }));
          }
        }
        from = idx + len;
      }
    }
  });
  return DecorationSet.create(doc, decos);
}

export const HeatmapExtension = Extension.create({
  name: 'heatmap',
  addStorage() {
    return { terms: [] as HeatTerm[], enabled: false };
  },
  addProseMirrorPlugins() {
    const storage = this.storage;
    return [
      new Plugin({
        key: heatmapPluginKey,
        state: {
          init() {
            return {
              terms: storage.terms as HeatTerm[], sorted: [] as SortedTerm[],
              enabled: storage.enabled as boolean, decorations: DecorationSet.empty,
            } satisfies HeatmapPluginState;
          },
          apply(tr, prev, _old, newState) {
            const meta = tr.getMeta(heatmapPluginKey);
            if (meta) {
              const terms = meta.terms ?? prev.terms;
              const enabled = meta.enabled ?? prev.enabled;
              const sorted = meta.terms ? sortTerms(terms) : prev.sorted;
              return {
                terms, sorted, enabled,
                decorations: enabled ? buildDecorations(newState.doc, sorted) : DecorationSet.empty,
              };
            }
            if (tr.docChanged && prev.enabled) {
              return { ...prev, decorations: buildDecorations(newState.doc, prev.sorted) };
            }
            return prev;
          },
        },
        props: {
          decorations(state) {
            return heatmapPluginKey.getState(state)?.decorations ?? DecorationSet.empty;
          },
        },
      }),
    ];
  },
});

export function setHeatmapTerms(editor: any, terms: HeatTerm[]) {
  editor.view.dispatch(editor.view.state.tr.setMeta(heatmapPluginKey, { terms }));
}

export function setHeatmapEnabled(editor: any, enabled: boolean) {
  editor.view.dispatch(editor.view.state.tr.setMeta(heatmapPluginKey, { enabled }));
}
