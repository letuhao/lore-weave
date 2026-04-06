import { Extension } from '@tiptap/core';
import { Plugin, PluginKey } from '@tiptap/pm/state';
import { toast } from 'sonner';

/**
 * Media block types that are protected in Classic mode.
 * Backspace/Delete at boundaries of these nodes is blocked.
 */
const MEDIA_NODE_TYPES = new Set(['imageBlock', 'codeBlock', 'videoBlock', 'audioBlock']);

/** Atom nodes (no editable content inside) — need extra backspace protection in all modes */
const ATOM_MEDIA_TYPES = new Set(['imageBlock', 'videoBlock', 'audioBlock']);

const mediaGuardKey = new PluginKey('mediaGuard');

/** Debounce toast so it doesn't spam on repeated keypresses */
let lastToastTime = 0;
function showGuardToast(isClassic: boolean) {
  const now = Date.now();
  if (now - lastToastTime < 2000) return; // 2s debounce
  lastToastTime = now;
  if (isClassic) {
    toast.info('Media blocks are protected in Classic mode. Switch to AI mode to edit or delete.', {
      duration: 3000,
    });
  }
}

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
                    showGuardToast(isClassic);
                    return true;
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
                    showGuardToast(isClassic);
                    return true;
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
                showGuardToast(isClassic);
                return true;
              }
            }

            // --- Classic mode: block paste over selection containing media ---
            if (isClassic && (event.key.toLowerCase() === 'v' && (event.ctrlKey || event.metaKey)) && !empty) {
              let hasMedia = false;
              state.doc.nodesBetween($from.pos, $to.pos, (node) => {
                if (MEDIA_NODE_TYPES.has(node.type.name)) {
                  hasMedia = true;
                }
              });
              if (hasMedia) {
                showGuardToast(isClassic);
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
