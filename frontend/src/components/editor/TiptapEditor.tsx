import { useEditor, EditorContent, type Editor, type JSONContent } from '@tiptap/react';
import { SourceView } from './SourceView';
import StarterKit from '@tiptap/starter-kit';
import Placeholder from '@tiptap/extension-placeholder';
import Typography from '@tiptap/extension-typography';
import { useState, useEffect, useCallback, useRef, useImperativeHandle, forwardRef } from 'react';
import { FormatToolbar } from './FormatToolbar';
import { CodeBlockToolbar } from './CodeBlockToolbar';
import { SlashMenuExtension, SlashMenuPopup, type EditorMode } from './SlashMenu';
import { CalloutExtension } from './CalloutNode';
import { CodeBlockExtension } from './CodeBlockNode';
import { ImageBlockExtension } from './ImageBlockNode';
import { VideoBlockExtension } from './VideoBlockNode';
import { AudioBlockExtension } from './AudioBlockNode';
import { AudioAttrsExtension } from './AudioAttrsExtension';
import { AudioAttachBarExtension } from './AudioAttachBarExtension';
import { AudioAttachActionsExtension } from './AudioAttachActionsExtension';
import { MediaGuardExtension } from './MediaGuardExtension';
import Link from '@tiptap/extension-link';
import Underline from '@tiptap/extension-underline';
import Highlight from '@tiptap/extension-highlight';
import Subscript from '@tiptap/extension-subscript';
import Superscript from '@tiptap/extension-superscript';
import GlobalDragHandle from 'tiptap-extension-global-drag-handle';
import { GrammarExtension, setGrammarEnabled } from './GrammarPlugin';
import { GlossaryExtension, setGlossaryEntities, setGlossaryEnabled, getGlossaryCount } from './GlossaryPlugin';
import { CitationMark } from './CitationMark';

export interface TiptapEditorHandle {
  /** Reset editor content from Tiptap JSON (e.g. revision restore, discard) */
  setContent: (json: any) => void;
  /** Toggle grammar checking */
  setGrammarEnabled: (enabled: boolean) => void;
  /** Toggle source view */
  setSourceView: (show: boolean) => void;
  /** Set glossary entities for decoration scanning */
  setGlossaryEntities: (entities: import('@/features/glossary/types').EntityNameEntry[]) => void;
  /** Toggle glossary highlights on/off */
  setGlossaryEnabled: (enabled: boolean) => void;
  /** Get current glossary match count */
  getGlossaryCount: () => number;
  /** ARCH-1 C6 — current selection (ProseMirror positions + selected text),
   *  or null if the editor isn't ready. `empty` = a caret with no selection. */
  getSelection: () => { from: number; to: number; empty: boolean; text: string } | null;
  /** ARCH-1 C6 — insert plain text at the cursor. Returns false if no editor.
   *  Flows through onUpdate (NOT setContent) so it dirties + autosaves. */
  insertAtCursor: (text: string) => boolean;
  /** ARCH-1 C6 — replace the current selection with text. Returns false if
   *  there is no (non-empty) selection. One chained transaction = one undo. */
  replaceSelection: (text: string) => boolean;
}

interface TiptapEditorProps {
  content: any;
  /** Fires on every doc mutation (typing OR programmatic insert via the handle).
   *  `text` is the editor's live plain text — lets hosts keep char/word counters
   *  in sync without re-deriving from JSON. */
  onUpdate: (json: any, text: string) => void;
  editable?: boolean;
  grammarEnabled?: boolean;
  editorMode?: EditorMode;
  className?: string;
  /** T3.2: host-supplied floating menu bound to the live editor (e.g. the
   *  composition Selection Tools). Rendered inside, only when editable, with the
   *  editor instance. Default: nothing (other hosts unaffected). */
  selectionMenu?: (editor: Editor) => React.ReactNode;
}

import { extractText, addTextSnapshots } from '@/lib/tiptap-utils';
// Re-export from shared utility (keeps existing imports working)
export { extractText, addTextSnapshots };
export { setGlossaryEntities, setGlossaryEnabled, getGlossaryCount };

export const TiptapEditor = forwardRef<TiptapEditorHandle, TiptapEditorProps>(
  function TiptapEditor({ content, onUpdate, editable = true, grammarEnabled = true, editorMode = 'classic', className, selectionMenu }, ref) {
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
        AudioBlockExtension,
        AudioAttrsExtension,
        AudioAttachBarExtension,
        AudioAttachActionsExtension,
        MediaGuardExtension,
        Link.configure({
          openOnClick: false,
          HTMLAttributes: { target: '_blank', rel: 'noopener noreferrer' },
        }),
        Underline,
        Highlight.configure({ multicolor: false }),
        Subscript,
        Superscript,
        CitationMark, // wiki-llm M7a — preserve AI citation provenance through edits

        GlobalDragHandle.configure({
          dragHandleWidth: 20,
        }),
        Placeholder.configure({
          placeholder: 'Type / for commands...',
        }),
        Typography,
        CalloutExtension,
        GrammarExtension,
        GlossaryExtension,
        SlashMenuExtension,
      ],
      content: initialContent.current,
      editable,
      onUpdate: ({ editor }) => {
        if (isExternalUpdate.current) return;
        onUpdate(addTextSnapshots(editor.getJSON()), editor.getText());
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
      if (!editor) return;
      (editor.storage as any).mediaGuard.editorMode = editorMode;

      // Force re-render of all media NodeViews by touching their attrs.
      // React NodeViews only re-render when their node changes — storage changes alone don't trigger it.
      const mediaTypes = new Set(['imageBlock', 'videoBlock']);
      const { tr } = editor.state;
      let touched = false;
      editor.state.doc.descendants((node, pos) => {
        if (mediaTypes.has(node.type.name)) {
          // Set a _mode attr (not persisted, just forces React re-render)
          tr.setNodeMarkup(pos, undefined, { ...node.attrs, _mode: editorMode });
          touched = true;
        }
      });
      if (touched) {
        tr.setMeta('addToHistory', false); // Don't pollute undo history
        editor.view.dispatch(tr);
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
      setGlossaryEntities: (entities) => {
        if (editor) setGlossaryEntities(editor, entities);
      },
      setGlossaryEnabled: (enabled: boolean) => {
        if (editor) setGlossaryEnabled(editor, enabled);
      },
      getGlossaryCount: () => {
        if (editor) return getGlossaryCount(editor);
        return 0;
      },
      // ARCH-1 C6 — editor write-back for AG-UI frontend tools. These mutate
      // through editor.chain() (NOT setContent), so onUpdate fires and the doc
      // dirties/autosaves exactly like typing. We deliberately do NOT set
      // isExternalUpdate here.
      getSelection: () => {
        if (!editor) return null;
        const { from, to, empty } = editor.state.selection;
        return { from, to, empty, text: editor.state.doc.textBetween(from, to, ' ') };
      },
      insertAtCursor: (text: string) => {
        if (!editor || !text) return false;
        editor.chain().focus().insertContentAt(editor.state.selection.from, text).run();
        return true;
      },
      replaceSelection: (text: string) => {
        if (!editor) return false;
        const { from, to, empty } = editor.state.selection;
        if (empty) return false;  // nothing selected — caller falls back / toasts
        editor.chain().focus().deleteRange({ from, to }).insertContentAt(from, text).run();
        return true;
      },
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
            {editable && <CodeBlockToolbar editor={editor} />}
            {editable && selectionMenu?.(editor)}
          </>
        )}
      </div>
    );
  },
);
