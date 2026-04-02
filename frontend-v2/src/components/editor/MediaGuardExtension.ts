import { Extension } from '@tiptap/core';
import { Plugin, PluginKey } from '@tiptap/pm/state';

/**
 * Media block types that are protected in Classic mode.
 * Backspace/Delete at boundaries of these nodes is blocked.
 */
const MEDIA_NODE_TYPES = new Set(['imageBlock', 'codeBlock', 'videoBlock']);

const mediaGuardKey = new PluginKey('mediaGuard');

/**
 * Tiptap extension that protects media blocks from accidental deletion
 * in Classic mode. In AI mode, all default behaviors apply.
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
            if (storage.editorMode !== 'classic') return false;

            const { state } = view;
            const { selection } = state;
            const { $from, $to, empty } = selection;

            // --- Backspace at start of block after a media node ---
            if (event.key === 'Backspace' && empty) {
              // Check if cursor is at the very start of a text block
              if ($from.parentOffset === 0 && $from.depth > 0) {
                const posBefore = $from.before($from.depth);
                if (posBefore > 0) {
                  const nodeBefore = state.doc.resolve(posBefore).nodeBefore;
                  if (nodeBefore && MEDIA_NODE_TYPES.has(nodeBefore.type.name)) {
                    return true; // Block the keypress
                  }
                }
              }
            }

            // --- Delete at end of block before a media node ---
            if (event.key === 'Delete' && empty) {
              if ($from.parentOffset === $from.parent.content.size && $from.depth > 0) {
                const posAfter = $from.after($from.depth);
                if (posAfter < state.doc.content.size) {
                  const nodeAfter = state.doc.resolve(posAfter).nodeAfter;
                  if (nodeAfter && MEDIA_NODE_TYPES.has(nodeAfter.type.name)) {
                    return true; // Block the keypress
                  }
                }
              }
            }

            // --- Backspace/Delete with selection spanning media nodes ---
            if ((event.key === 'Backspace' || event.key === 'Delete') && !empty) {
              // Check if any media node is within the selection range
              let hasMedia = false;
              state.doc.nodesBetween($from.pos, $to.pos, (node) => {
                if (MEDIA_NODE_TYPES.has(node.type.name)) {
                  hasMedia = true;
                }
              });
              if (hasMedia) {
                // Delete only text content, preserve media nodes
                // For simplicity, block the entire delete if media is in selection
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
