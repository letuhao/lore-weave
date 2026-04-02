import { useEditor, EditorContent, type JSONContent } from '@tiptap/react';
import { SourceView } from './SourceView';
import StarterKit from '@tiptap/starter-kit';
import Placeholder from '@tiptap/extension-placeholder';
import Typography from '@tiptap/extension-typography';
import { useState, useEffect, useCallback, useRef, useImperativeHandle, forwardRef } from 'react';
import { FormatToolbar } from './FormatToolbar';
import { SlashMenuExtension, SlashMenuPopup, type EditorMode } from './SlashMenu';
import { CalloutExtension } from './CalloutNode';
import { CodeBlockExtension } from './CodeBlockNode';
import { ImageBlockExtension } from './ImageBlockNode';
import { VideoBlockExtension } from './VideoBlockNode';
import { MediaGuardExtension } from './MediaGuardExtension';
import { GrammarExtension, setGrammarEnabled } from './GrammarPlugin';

export interface TiptapEditorHandle {
  /** Reset editor content from Tiptap JSON (e.g. revision restore, discard) */
  setContent: (json: any) => void;
  /** Toggle grammar checking */
  setGrammarEnabled: (enabled: boolean) => void;
  /** Toggle source view */
  setSourceView: (show: boolean) => void;
}

interface TiptapEditorProps {
  content: any;
  onUpdate: (json: any) => void;
  editable?: boolean;
  grammarEnabled?: boolean;
  editorMode?: EditorMode;
  className?: string;
}

/** Recursively extract plain text from a Tiptap node */
export function extractText(node: JSONContent): string {
  if (node.type === 'text') return node.text || '';
  if (node.type === 'hardBreak') return '\n';
  // Atom nodes with no children — extract meaningful text from attrs
  if (node.type === 'imageBlock') return (node.attrs?.alt as string) || '';
  if (node.type === 'videoBlock') return (node.attrs?.caption as string) || '';
  if (!node.content) return '';
  return node.content
    .map(child => extractText(child))
    .join(node.type === 'listItem' ? '\n' : '');
}

/** Add _text snapshot to each top-level block for the chapter_blocks trigger */
export function addTextSnapshots(doc: JSONContent): JSONContent {
  if (!doc.content) return doc;
  return {
    ...doc,
    content: doc.content.map(block => ({
      ...block,
      _text: extractText(block),
    })),
  };
}

export const TiptapEditor = forwardRef<TiptapEditorHandle, TiptapEditorProps>(
  function TiptapEditor({ content, onUpdate, editable = true, grammarEnabled = true, editorMode = 'classic', className }, ref) {
    const initialContent = useRef(content);
    const prevContent = useRef(content);
    const isExternalUpdate = useRef(false);
    const [showSource, setShowSource] = useState(false);

    const editor = useEditor({
      extensions: [
        StarterKit.configure({
          heading: { levels: [1, 2, 3] },
          horizontalRule: {},
          codeBlock: false, // replaced by CodeBlockExtension (lowlight)
        }),
        CodeBlockExtension,
        ImageBlockExtension,
        VideoBlockExtension,
        MediaGuardExtension,
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
        onUpdate(addTextSnapshots(editor.getJSON()));
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
      editor.commands.setContent(content);
      isExternalUpdate.current = false;
    }, [editor, content]);

    // Sync grammar enabled state
    useEffect(() => {
      if (editor) setGrammarEnabled(editor, grammarEnabled);
    }, [editor, grammarEnabled]);

    // Sync editor mode to extension storage (used by MediaGuardExtension + NodeViews)
    useEffect(() => {
      if (editor) {
        (editor.storage as any).mediaGuard.editorMode = editorMode;
        // Force re-render of NodeViews so they pick up the mode change
        editor.view.dispatch(editor.state.tr.setMeta('editorModeChanged', editorMode));
      }
    }, [editor, editorMode]);

    const setContentHandler = useCallback((newContent: any) => {
      if (!editor) return;
      isExternalUpdate.current = true;
      editor.commands.setContent(newContent);
      isExternalUpdate.current = false;
    }, [editor]);

    useImperativeHandle(ref, () => ({
      setContent: setContentHandler,
      setGrammarEnabled: (enabled: boolean) => {
        if (editor) setGrammarEnabled(editor, enabled);
      },
      setSourceView: (show: boolean) => setShowSource(show),
    }), [setContentHandler, editor]);

    if (!editor) return null;

    return (
      <div className={`${className ?? ''} tiptap-editor-wrapper relative`}>
        {editable && <FormatToolbar editor={editor} mode={editorMode} />}
        {showSource ? (
          <SourceView json={editor.getJSON()} />
        ) : (
          <>
            <EditorContent editor={editor} />
            {editable && <SlashMenuPopup editor={editor} mode={editorMode} />}
          </>
        )}
      </div>
    );
  },
);
