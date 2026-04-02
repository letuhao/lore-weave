import { Extension } from '@tiptap/core';
import { Plugin, PluginKey } from '@tiptap/pm/state';

/**
 * Media block types that are protected in Classic mode.
 * Backspace/Delete at boundaries of these nodes is blocked.
 */
const MEDIA_NODE_TYPES = new Set(['imageBlock', 'codeBlock', 'videoBlock']);

/** Atom nodes (no editable content inside) — need extra backspace protection in all modes */
const ATOM_MEDIA_TYPES = new Set(['imageBlock', 'videoBlock']);

const mediaGuardKey = new PluginKey('mediaGuard');

/**
 * Tiptap extension that protects media blocks from accidental deletion.
 *
 * Classic mode: all media blocks (image, video, code) are fully locked.
 * AI mode: atom blocks (image, video) are protected from backspace-at-boundary
 *   but can be deleted via the node's delete button or by selecting + delete.
 */
export const MediaGuardExtension = Extension.create({
  name: 'mediaGuard',

  addStorage() {
    return {
      editorMode: 'ai' as 'classic' | 'ai',
    };
  },

  addProseMirrorPlugins() {
    const storage = this.storage;

    return [
      new Plugin({
        key: mediaGuardKey,

        props: {
          handleKeyDown(view, event) {
            const isClassic = storage.editorMode === 'classic';
            const { state } = view;
            const { selection } = state;
            const { $from, $to, empty } = selection;

            // Determine which node types to guard based on mode
            const guardedTypes = isClassic ? MEDIA_NODE_TYPES : ATOM_MEDIA_TYPES;

            // --- Backspace at start of block after a guarded node ---
            if (event.key === 'Backspace' && empty) {
              if ($from.parentOffset === 0 && $from.depth > 0) {
                const posBefore = $from.before($from.depth);
                if (posBefore > 0) {
                  const nodeBefore = state.doc.resolve(posBefore).nodeBefore;
                  if (nodeBefore && guardedTypes.has(nodeBefore.type.name)) {
                    return true; // Block the keypress
                  }
                }
              }
            }

            // --- Delete at end of block before a guarded node ---
            if (event.key === 'Delete' && empty) {
              if ($from.parentOffset === $from.parent.content.size && $from.depth > 0) {
                const posAfter = $from.after($from.depth);
                if (posAfter < state.doc.content.size) {
                  const nodeAfter = state.doc.resolve(posAfter).nodeAfter;
                  if (nodeAfter && guardedTypes.has(nodeAfter.type.name)) {
                    return true; // Block the keypress
                  }
                }
              }
            }

            // --- Classic mode only: block deletion of selection spanning media ---
            if (isClassic && (event.key === 'Backspace' || event.key === 'Delete') && !empty) {
              let hasMedia = false;
              state.doc.nodesBetween($from.pos, $to.pos, (node) => {
                if (MEDIA_NODE_TYPES.has(node.type.name)) {
                  hasMedia = true;
                }
              });
              if (hasMedia) {
                return true;
              }
            }

            return false;
          },
        },
      }),
    ];
  },
});
