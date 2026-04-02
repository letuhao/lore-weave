import { useEffect, useState, useCallback } from 'react';
import type { Editor } from '@tiptap/react';
import { Copy, Check, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { CODE_LANGUAGES } from './CodeBlockNode';

interface CodeBlockToolbarProps {
  editor: Editor;
}

/**
 * Floating toolbar that appears when the cursor is inside a code block.
 * Shows language selector, copy button, and delete button.
 * Positioned absolutely relative to the editor wrapper.
 */
export function CodeBlockToolbar({ editor }: CodeBlockToolbarProps) {
  const [visible, setVisible] = useState(false);
  const [language, setLanguage] = useState('plaintext');
  const [pos, setPos] = useState({ top: 0, right: 0 });
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const update = () => {
      const { state } = editor;
      const { $from } = state.selection;

      // Check if cursor is inside a codeBlock
      let codeBlockNode = null;
      let codeBlockPos = -1;
      for (let d = $from.depth; d >= 0; d--) {
        const node = $from.node(d);
        if (node.type.name === 'codeBlock') {
          codeBlockNode = node;
          codeBlockPos = $from.before(d);
          break;
        }
      }

      if (!codeBlockNode || codeBlockPos < 0) {
        setVisible(false);
        return;
      }

      setVisible(true);
      setLanguage(codeBlockNode.attrs.language || 'plaintext');

      // Position the toolbar at the top-right of the code block
      try {
        const coords = editor.view.coordsAtPos(codeBlockPos);
        const editorRect = editor.view.dom.closest('.tiptap-editor-wrapper')?.getBoundingClientRect();
        if (editorRect) {
          setPos({
            top: coords.top - editorRect.top - 2,
            right: 8,
          });
        }
      } catch {
        // coordsAtPos can throw for invalid positions
      }
    };

    editor.on('selectionUpdate', update);
    editor.on('transaction', update);
    return () => {
      editor.off('selectionUpdate', update);
      editor.off('transaction', update);
    };
  }, [editor]);

  const handleLanguageChange = useCallback(
    (e: React.ChangeEvent<HTMLSelectElement>) => {
      const newLang = e.target.value;
      const { state } = editor;
      const { $from } = state.selection;

      for (let d = $from.depth; d >= 0; d--) {
        if ($from.node(d).type.name === 'codeBlock') {
          const pos = $from.before(d);
          editor.chain().focus().command(({ tr }) => {
            tr.setNodeMarkup(pos, undefined, { ...$from.node(d).attrs, language: newLang });
            return true;
          }).run();
          break;
        }
      }
    },
    [editor],
  );

  const handleCopy = useCallback(() => {
    const { state } = editor;
    const { $from } = state.selection;
    for (let d = $from.depth; d >= 0; d--) {
      if ($from.node(d).type.name === 'codeBlock') {
        const text = $from.node(d).textContent;
        navigator.clipboard.writeText(text).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        }, () => {});
        break;
      }
    }
  }, [editor]);

  const handleDelete = useCallback(() => {
    const { state } = editor;
    const { $from } = state.selection;
    for (let d = $from.depth; d >= 0; d--) {
      if ($from.node(d).type.name === 'codeBlock') {
        const pos = $from.before(d);
        const node = $from.node(d);
        editor.chain().focus().deleteRange({ from: pos, to: pos + node.nodeSize }).run();
        break;
      }
    }
  }, [editor]);

  if (!visible) return null;

  return (
    <div
      className="pointer-events-auto absolute z-40 flex items-center gap-1 rounded-md border bg-card px-1.5 py-1 shadow-md"
      style={{ top: pos.top, right: pos.right }}
      contentEditable={false}
      // Prevent clicks from stealing editor focus
      onMouseDown={(e) => e.preventDefault()}
    >
      <select
        value={language}
        onChange={handleLanguageChange}
        aria-label="Code language"
        className="rounded border bg-input px-1.5 py-0.5 font-mono text-[10px] text-foreground outline-none"
        onMouseDown={(e) => e.stopPropagation()}
      >
        {CODE_LANGUAGES.map((lang) => (
          <option key={lang.value} value={lang.value}>
            {lang.label}
          </option>
        ))}
      </select>

      <button
        type="button"
        onClick={handleCopy}
        className={cn(
          'flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] transition-colors',
          copied ? 'text-success' : 'text-muted-foreground hover:bg-secondary hover:text-foreground',
        )}
        title="Copy code"
      >
        {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
      </button>

      <button
        type="button"
        onClick={handleDelete}
        className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
        title="Delete code block"
      >
        <Trash2 className="h-3 w-3" />
      </button>
    </div>
  );
}
