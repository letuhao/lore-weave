import { useState, useEffect, useCallback, useRef } from 'react';
import { Extension } from '@tiptap/core';
import { Plugin, PluginKey } from '@tiptap/pm/state';
import { Decoration, DecorationSet } from '@tiptap/pm/view';
import type { Editor } from '@tiptap/react';
import {
  Pilcrow, Heading1, Heading2, Heading3, Minus, List, ListOrdered, Quote, MessageSquareText, Code2,
  ImageIcon, Video,
} from 'lucide-react';
import { cn } from '@/lib/utils';

export type EditorMode = 'classic' | 'ai';

interface SlashMenuItem {
  title: string;
  description: string;
  icon: React.ReactNode;
  command: (editor: Editor) => void;
  /** If set, only show in these modes. If unset, show in all modes. */
  modes?: EditorMode[];
}

const SLASH_ITEMS: SlashMenuItem[] = [
  {
    title: 'Paragraph',
    description: 'Plain text block',
    icon: <Pilcrow className="h-4 w-4" />,
    command: (editor) => editor.chain().focus().setParagraph().run(),
  },
  {
    title: 'Heading 1',
    description: 'Large section heading',
    icon: <Heading1 className="h-4 w-4" />,
    command: (editor) => editor.chain().focus().toggleHeading({ level: 1 }).run(),
  },
  {
    title: 'Heading 2',
    description: 'Medium section heading',
    icon: <Heading2 className="h-4 w-4" />,
    command: (editor) => editor.chain().focus().toggleHeading({ level: 2 }).run(),
  },
  {
    title: 'Heading 3',
    description: 'Small section heading',
    icon: <Heading3 className="h-4 w-4" />,
    command: (editor) => editor.chain().focus().toggleHeading({ level: 3 }).run(),
  },
  {
    title: 'Bullet List',
    description: 'Unordered list',
    icon: <List className="h-4 w-4" />,
    command: (editor) => editor.chain().focus().toggleBulletList().run(),
  },
  {
    title: 'Numbered List',
    description: 'Ordered list',
    icon: <ListOrdered className="h-4 w-4" />,
    command: (editor) => editor.chain().focus().toggleOrderedList().run(),
  },
  {
    title: 'Quote',
    description: 'Block quotation',
    icon: <Quote className="h-4 w-4" />,
    command: (editor) => editor.chain().focus().toggleBlockquote().run(),
  },
  {
    title: 'Image',
    description: 'Upload, paste, or AI generate',
    icon: <ImageIcon className="h-4 w-4" />,
    command: (editor) => editor.chain().focus().insertContent({ type: 'imageBlock' }).run(),
    modes: ['ai'],
  },
  {
    title: 'Video',
    description: 'Upload video file',
    icon: <Video className="h-4 w-4" />,
    command: (editor) => editor.chain().focus().insertContent({ type: 'videoBlock' }).run(),
    modes: ['ai'],
  },
  {
    title: 'Code Block',
    description: 'Syntax highlighted code',
    icon: <Code2 className="h-4 w-4" />,
    command: (editor) => editor.chain().focus().toggleCodeBlock().run(),
  },
  {
    title: 'Callout',
    description: 'Author note or tip',
    icon: <MessageSquareText className="h-4 w-4" />,
    command: (editor) => editor.chain().focus().insertContent({ type: 'callout', attrs: { type: 'note' } }).run(),
    modes: ['ai'],
  },
  {
    title: 'Divider',
    description: 'Horizontal rule',
    icon: <Minus className="h-4 w-4" />,
    command: (editor) => editor.chain().focus().setHorizontalRule().run(),
  },
];

const slashMenuPluginKey = new PluginKey('slashMenu');

export interface SlashMenuState {
  active: boolean;
  query: string;
  from: number;
  to: number;
}

/**
 * Tiptap extension that detects `/` at the start of a block and opens a slash menu.
 * The actual popup rendering is done by the SlashMenuPopup React component.
 */
export const SlashMenuExtension = Extension.create({
  name: 'slashMenu',

  addProseMirrorPlugins() {
    return [
      new Plugin({
        key: slashMenuPluginKey,
        state: {
          init(): SlashMenuState {
            return { active: false, query: '', from: 0, to: 0 };
          },
          apply(tr, prev): SlashMenuState {
            const sel = tr.selection;
            if (!sel.empty) return { active: false, query: '', from: 0, to: 0 };

            const pos = sel.$from;
            const textBefore = pos.parent.textContent.slice(0, pos.parentOffset);

            // Check if we have /query at the start of the block
            const match = textBefore.match(/^\/(\w*)$/);
            if (match) {
              const blockStart = pos.before(pos.depth) + 1;
              return {
                active: true,
                query: match[1],
                from: blockStart,
                to: blockStart + textBefore.length,
              };
            }

            return { active: false, query: '', from: 0, to: 0 };
          },
        },
      }),
    ];
  },
});

/** Get the slash menu state from the editor */
export function getSlashMenuState(editor: Editor): SlashMenuState {
  return slashMenuPluginKey.getState(editor.state) ?? { active: false, query: '', from: 0, to: 0 };
}

/**
 * Floating slash menu popup — rendered in the TiptapEditor component.
 */
export function SlashMenuPopup({ editor, mode = 'ai' }: { editor: Editor; mode?: EditorMode }) {
  const [state, setState] = useState<SlashMenuState>({ active: false, query: '', from: 0, to: 0 });
  const [selectedIndex, setSelectedIndex] = useState(0);
  const menuRef = useRef<HTMLDivElement>(null);

  // Update state on every transaction
  useEffect(() => {
    const handler = () => {
      const s = getSlashMenuState(editor);
      setState(s);
      if (!s.active) setSelectedIndex(0);
    };
    editor.on('transaction', handler);
    return () => { editor.off('transaction', handler); };
  }, [editor]);

  const filtered = SLASH_ITEMS.filter((item) => {
    // Filter by mode
    if (item.modes && !item.modes.includes(mode)) return false;
    // Filter by query
    if (state.query && !item.title.toLowerCase().includes(state.query.toLowerCase())) return false;
    return true;
  });

  const executeItem = useCallback((item: SlashMenuItem) => {
    // Delete the /query text first
    editor.chain().focus().deleteRange({ from: state.from, to: state.to }).run();
    item.command(editor);
  }, [editor, state.from, state.to]);

  // Keyboard navigation
  useEffect(() => {
    if (!state.active) return;

    const handler = (e: KeyboardEvent) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIndex((i) => (i + 1) % filtered.length);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIndex((i) => (i - 1 + filtered.length) % filtered.length);
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (filtered[selectedIndex]) executeItem(filtered[selectedIndex]);
      } else if (e.key === 'Escape') {
        // Delete the slash to dismiss
        editor.chain().focus().deleteRange({ from: state.from, to: state.to }).run();
      }
    };

    document.addEventListener('keydown', handler, true);
    return () => document.removeEventListener('keydown', handler, true);
  }, [state.active, filtered, selectedIndex, executeItem, editor, state.from, state.to]);

  // Reset selection when query changes
  useEffect(() => {
    setSelectedIndex(0);
  }, [state.query]);

  if (!state.active || filtered.length === 0) return null;

  // Position the popup near the cursor
  const coords = editor.view.coordsAtPos(state.from);
  const editorRect = editor.view.dom.closest('.tiptap-editor-wrapper')?.getBoundingClientRect();
  const top = coords.bottom - (editorRect?.top ?? 0) + 4;
  const left = coords.left - (editorRect?.left ?? 0);

  return (
    <div
      ref={menuRef}
      className="absolute z-50 w-56 rounded-lg border bg-card shadow-lg"
      style={{ top, left }}
    >
      <div className="p-1">
        {filtered.map((item, i) => (
          <button
            key={item.title}
            className={cn(
              'flex w-full items-center gap-3 rounded-md px-2.5 py-2 text-left text-xs transition-colors',
              i === selectedIndex
                ? 'bg-primary/10 text-foreground'
                : 'text-muted-foreground hover:bg-secondary hover:text-foreground',
            )}
            onClick={() => executeItem(item)}
            onMouseEnter={() => setSelectedIndex(i)}
          >
            <span className="flex h-7 w-7 items-center justify-center rounded-md border bg-background">
              {item.icon}
            </span>
            <div>
              <div className="font-medium">{item.title}</div>
              <div className="text-[10px] opacity-60">{item.description}</div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
