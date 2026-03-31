import { Extension } from '@tiptap/core';
import { Plugin, PluginKey } from '@tiptap/pm/state';
import { Decoration, DecorationSet } from '@tiptap/pm/view';
import { checkGrammar, type GrammarMatch } from '@/features/grammar/api';

const grammarPluginKey = new PluginKey('grammar');

interface GrammarPluginState {
  decorations: DecorationSet;
  /** Track pending check timeouts by node position */
  version: number;
}

const DEBOUNCE_MS = 2000;

/**
 * Tiptap extension that runs LanguageTool grammar checks on text blocks
 * and renders inline wavy underline decorations.
 *
 * - Debounces checks (2s after last edit)
 * - Only checks text nodes (paragraphs, headings)
 * - Decorations show tooltip on hover with suggestion
 */
export const GrammarExtension = Extension.create({
  name: 'grammarCheck',

  addStorage() {
    return {
      enabled: true,
      debounceTimer: null as ReturnType<typeof setTimeout> | null,
      lastCheckedDoc: null as any,
    };
  },

  addProseMirrorPlugins() {
    const extension = this;

    return [
      new Plugin({
        key: grammarPluginKey,
        state: {
          init(): GrammarPluginState {
            return { decorations: DecorationSet.empty, version: 0 };
          },
          apply(tr, prev): GrammarPluginState {
            // Map decorations through document changes
            if (tr.docChanged) {
              return {
                decorations: prev.decorations.map(tr.mapping, tr.doc),
                version: prev.version,
              };
            }
            // Check for grammar results metadata
            const meta = tr.getMeta(grammarPluginKey);
            if (meta?.decorations) {
              return { decorations: meta.decorations, version: prev.version + 1 };
            }
            return prev;
          },
        },
        props: {
          decorations(state) {
            if (!extension.storage.enabled) return DecorationSet.empty;
            return grammarPluginKey.getState(state)?.decorations ?? DecorationSet.empty;
          },
        },
        view(editorView) {
          const scheduleCheck = () => {
            if (!extension.storage.enabled) return;
            if (extension.storage.debounceTimer) {
              clearTimeout(extension.storage.debounceTimer);
            }
            extension.storage.debounceTimer = setTimeout(() => {
              void runGrammarCheck(editorView);
            }, DEBOUNCE_MS);
          };

          // Run initial check after a short delay
          const initTimer = setTimeout(scheduleCheck, 1000);

          return {
            update(view, prevState) {
              if (!view.state.doc.eq(prevState.doc)) {
                scheduleCheck();
              }
            },
            destroy() {
              clearTimeout(initTimer);
              if (extension.storage.debounceTimer) {
                clearTimeout(extension.storage.debounceTimer);
              }
            },
          };
        },
      }),
    ];
  },
});

async function runGrammarCheck(view: any) {
  const { doc } = view.state;
  const docSnapshot = doc;

  // Collect text blocks to check
  const blocks: Array<{ from: number; text: string }> = [];
  doc.descendants((node: any, pos: number) => {
    if (node.isTextblock && node.textContent.trim()) {
      blocks.push({ from: pos + 1, text: node.textContent }); // +1 to skip the node's opening token
    }
    return true;
  });

  // Check all blocks in parallel
  const results = await Promise.all(
    blocks.map(async (block) => {
      const matches = await checkGrammar(block.text);
      return { block, matches };
    }),
  );

  // Doc may have changed during async grammar check — abort if so
  if (!view.state.doc.eq(docSnapshot)) return;

  const decorations: Decoration[] = [];
  for (const { block, matches } of results) {
    for (const match of matches) {
      const from = block.from + match.offset;
      const to = from + match.length;
      // Bounds check against current doc
      if (from < 0 || to > view.state.doc.content.size) continue;
      const tooltip = match.message +
        (match.replacements.length ? ` \u2192 ${match.replacements.join(', ')}` : '');

      decorations.push(
        Decoration.inline(from, to, {
          class: 'grammar-issue',
          title: tooltip,
        }),
      );
    }
  }

  // Apply decorations via transaction metadata
  const tr = view.state.tr.setMeta(grammarPluginKey, {
    decorations: DecorationSet.create(view.state.doc, decorations),
  });
  view.dispatch(tr);
}

/** Toggle grammar checking on/off */
export function setGrammarEnabled(editor: any, enabled: boolean) {
  const ext = editor.extensionManager.extensions.find((e: any) => e.name === 'grammarCheck');
  if (ext) {
    ext.storage.enabled = enabled;
    if (!enabled) {
      // Clear decorations
      const tr = editor.state.tr.setMeta(grammarPluginKey, {
        decorations: DecorationSet.empty,
      });
      editor.view.dispatch(tr);
    }
  }
}
