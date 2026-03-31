import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Placeholder from '@tiptap/extension-placeholder';
import Typography from '@tiptap/extension-typography';
import { useEffect, useCallback, useRef, useImperativeHandle, forwardRef } from 'react';
import { FormatToolbar } from './FormatToolbar';
import { SlashMenuExtension, SlashMenuPopup, type EditorMode } from './SlashMenu';
import { CalloutExtension } from './CalloutNode';
import { GrammarExtension, setGrammarEnabled } from './GrammarPlugin';

export interface TiptapEditorHandle {
  /** Reset editor content from plain text (e.g. revision restore, discard) */
  __setContentFromPlainText: (text: string) => void;
  /** Toggle grammar checking */
  setGrammarEnabled: (enabled: boolean) => void;
}

interface TiptapEditorProps {
  content: string;
  onUpdate: (html: string) => void;
  editable?: boolean;
  grammarEnabled?: boolean;
  editorMode?: EditorMode;
  className?: string;
}

/**
 * Convert plain text (double-newline separated paragraphs) to HTML paragraphs.
 * Used on initial load when backend stores plain text.
 */
function plainTextToHtml(text: string): string {
  if (!text.trim()) return '<p></p>';
  // If it already looks like HTML, return as-is
  if (text.trim().startsWith('<')) return text;
  // Normalize line endings (Windows \r\n → \n)
  const normalized = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  return normalized
    .split(/\n\n+/)
    .map((p) => `<p>${escapeHtml(p.trim()).replace(/\n/g, '<br>')}</p>`)
    .join('');
}

/**
 * Convert Tiptap HTML back to plain text (double-newline separated paragraphs).
 * Used on save to maintain backward compatibility with existing backend.
 */
export function htmlToPlainText(html: string): string {
  const div = document.createElement('div');
  div.innerHTML = html;
  const blocks: string[] = [];
  for (const child of div.children) {
    const tag = child.tagName.toLowerCase();
    if (tag === 'hr') {
      blocks.push('---');
    } else if (tag.match(/^h[1-6]$/)) {
      const level = parseInt(tag[1]);
      blocks.push('#'.repeat(level) + ' ' + (child.textContent ?? ''));
    } else {
      const clone = child.cloneNode(true) as HTMLElement;
      for (const br of clone.querySelectorAll('br')) {
        br.replaceWith('\n');
      }
      const text = clone.textContent ?? '';
      blocks.push(text);
    }
  }
  return blocks.join('\n\n');
}

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

export const TiptapEditor = forwardRef<TiptapEditorHandle, TiptapEditorProps>(
  function TiptapEditor({ content, onUpdate, editable = true, grammarEnabled = true, editorMode = 'classic', className }, ref) {
    const initialContent = useRef(plainTextToHtml(content));
    const prevContent = useRef(content);
    const isExternalUpdate = useRef(false);

    const editor = useEditor({
      extensions: [
        StarterKit.configure({
          heading: { levels: [1, 2, 3] },
          horizontalRule: {},
          codeBlock: false,
        }),
        Placeholder.configure({
          placeholder: 'Type / for commands...',
        }),
        Typography,
        CalloutExtension,
        GrammarExtension,
        SlashMenuExtension,
      ],
      content: initialContent.current,
      editable,
      onUpdate: ({ editor }) => {
        if (isExternalUpdate.current) return;
        onUpdate(editor.getHTML());
      },
      editorProps: {
        attributes: {
          class: 'tiptap-content outline-none',
        },
      },
    });

    useEffect(() => {
      if (editor) editor.setEditable(editable);
    }, [editor, editable]);

    // React to external content changes (e.g. loading a different chapter, save + reload)
    useEffect(() => {
      if (!editor || content === prevContent.current) return;
      prevContent.current = content;
      isExternalUpdate.current = true;
      editor.commands.setContent(plainTextToHtml(content));
      isExternalUpdate.current = false;
    }, [editor, content]);

    // Sync grammar enabled state
    useEffect(() => {
      if (editor) setGrammarEnabled(editor, grammarEnabled);
    }, [editor, grammarEnabled]);

    const setContentFromPlainText = useCallback((newContent: string) => {
      if (!editor) return;
      isExternalUpdate.current = true;
      editor.commands.setContent(plainTextToHtml(newContent));
      isExternalUpdate.current = false;
    }, [editor]);

    useImperativeHandle(ref, () => ({
      __setContentFromPlainText: setContentFromPlainText,
      setGrammarEnabled: (enabled: boolean) => {
        if (editor) setGrammarEnabled(editor, enabled);
      },
    }), [setContentFromPlainText, editor]);

    if (!editor) return null;

    return (
      <div className={`${className ?? ''} tiptap-editor-wrapper relative`}>
        <FormatToolbar editor={editor} mode={editorMode} />
        <EditorContent editor={editor} />
        <SlashMenuPopup editor={editor} mode={editorMode} />
      </div>
    );
  },
);

export { plainTextToHtml };
