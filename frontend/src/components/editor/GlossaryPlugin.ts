import { Extension } from '@tiptap/core';
import { Plugin, PluginKey } from '@tiptap/pm/state';
import { Decoration, DecorationSet } from '@tiptap/pm/view';
import type { EntityNameEntry } from '@/features/glossary/types';

export const glossaryPluginKey = new PluginKey('glossary');

export type GlossaryPluginState = {
  entities: EntityNameEntry[];
  enabled: boolean;
  decorations: DecorationSet;
};

function buildDecorations(doc: any, entities: EntityNameEntry[]): DecorationSet {
  if (entities.length === 0) return DecorationSet.empty;

  const decos: Decoration[] = [];

  // Sort by name length descending so longer names match first (e.g. "Ancient Capital" before "Capital")
  const sorted = [...entities].sort((a, b) => b.display_name.length - a.display_name.length);

  doc.descendants((node: any, pos: number) => {
    if (!node.isText || !node.text) return;
    const text = node.text as string;

    // Track occupied positions to avoid overlapping decorations
    const occupied = new Set<number>();

    for (const entity of sorted) {
      const name = entity.display_name;
      if (name.length < 2) continue;

      let searchFrom = 0;
      while (searchFrom < text.length) {
        const idx = text.indexOf(name, searchFrom);
        if (idx === -1) break;

        // Check word boundaries (don't match partial words)
        const before = idx > 0 ? text[idx - 1] : ' ';
        const after = idx + name.length < text.length ? text[idx + name.length] : ' ';
        const isWord = /[\s.,;:!?()\[\]{}"""''—–\-\/]/.test(before) || idx === 0;
        const isWordEnd = /[\s.,;:!?()\[\]{}"""''—–\-\/]/.test(after) || idx + name.length === text.length;

        if (isWord && isWordEnd) {
          // Check no overlap
          let overlaps = false;
          for (let i = idx; i < idx + name.length; i++) {
            if (occupied.has(i)) { overlaps = true; break; }
          }
          if (!overlaps) {
            const from = pos + idx;
            const to = pos + idx + name.length;
            for (let i = idx; i < idx + name.length; i++) occupied.add(i);

            decos.push(Decoration.inline(from, to, {
              class: `glossary-mark glossary-kind-${entity.kind_code || 'default'}`,
              'data-entity-id': entity.entity_id,
              'data-entity-name': entity.display_name,
              'data-kind-code': entity.kind_code || '',
              'data-kind-color': entity.kind_color || '',
              'data-kind-icon': entity.kind_icon || '',
              'data-kind-name': entity.kind_name || '',
            }));
          }
        }

        searchFrom = idx + name.length;
      }
    }
  });

  return DecorationSet.create(doc, decos);
}

export const GlossaryExtension = Extension.create({
  name: 'glossary',

  addStorage() {
    return {
      entities: [] as EntityNameEntry[],
      enabled: true,
    };
  },

  addProseMirrorPlugins() {
    const storage = this.storage;

    return [
      new Plugin({
        key: glossaryPluginKey,
        state: {
          init(_, { doc }) {
            return {
              entities: storage.entities as EntityNameEntry[],
              enabled: storage.enabled as boolean,
              decorations: DecorationSet.empty,
            } satisfies GlossaryPluginState;
          },
          apply(tr, prev, _oldState, newState) {
            const meta = tr.getMeta(glossaryPluginKey);
            if (meta) {
              const entities = meta.entities ?? prev.entities;
              const enabled = meta.enabled ?? prev.enabled;
              const decorations = enabled
                ? buildDecorations(newState.doc, entities)
                : DecorationSet.empty;
              return { entities, enabled, decorations };
            }
            if (tr.docChanged && prev.enabled) {
              return {
                ...prev,
                decorations: buildDecorations(newState.doc, prev.entities),
              };
            }
            return prev;
          },
        },
        props: {
          decorations(state) {
            return glossaryPluginKey.getState(state)?.decorations ?? DecorationSet.empty;
          },
        },
      }),
    ];
  },
});

/** Set glossary entities on the editor (triggers re-scan) */
export function setGlossaryEntities(editor: any, entities: EntityNameEntry[]) {
  editor.view.dispatch(
    editor.view.state.tr.setMeta(glossaryPluginKey, { entities }),
  );
}

/** Toggle glossary highlights on/off */
export function setGlossaryEnabled(editor: any, enabled: boolean) {
  editor.view.dispatch(
    editor.view.state.tr.setMeta(glossaryPluginKey, { enabled }),
  );
}

/** Get current glossary decoration count */
export function getGlossaryCount(editor: any): number {
  const state = glossaryPluginKey.getState(editor.view.state);
  if (!state) return 0;
  let count = 0;
  state.decorations.find(undefined, undefined, () => { count++; return false; });
  return count;
}
