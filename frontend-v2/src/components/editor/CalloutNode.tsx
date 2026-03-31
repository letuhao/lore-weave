import { Node, mergeAttributes } from '@tiptap/core';
import { ReactNodeViewRenderer, NodeViewWrapper, NodeViewContent } from '@tiptap/react';
import { MessageSquareText } from 'lucide-react';

/**
 * Callout block node for author notes, warnings, tips, etc.
 * Rendered as a colored sidebar block in the editor.
 */
export const CalloutExtension = Node.create({
  name: 'callout',
  group: 'block',
  content: 'inline*',

  addAttributes() {
    return {
      type: {
        default: 'note',
        parseHTML: (element) => element.getAttribute('data-callout-type') || 'note',
        renderHTML: (attributes) => ({ 'data-callout-type': attributes.type }),
      },
    };
  },

  parseHTML() {
    return [{ tag: 'div[data-callout]' }];
  },

  renderHTML({ HTMLAttributes }) {
    return ['div', mergeAttributes(HTMLAttributes, { 'data-callout': '' }), 0];
  },

  addNodeView() {
    return ReactNodeViewRenderer(CalloutNodeView);
  },

  addKeyboardShortcuts() {
    return {
      // Enter at end of callout creates a new paragraph after it
      Enter: ({ editor }) => {
        if (!editor.isActive('callout')) return false;
        const { $from } = editor.state.selection;
        // If at the end of the callout's content, exit the callout
        if ($from.parentOffset === $from.parent.content.size) {
          return editor.chain().focus().insertContentAt(editor.state.selection.$to.after(), { type: 'paragraph' }).run();
        }
        return false;
      },
    };
  },
});

const CALLOUT_STYLES: Record<string, { border: string; bg: string; icon: string }> = {
  note:    { border: 'border-l-info',    bg: 'bg-info/5',    icon: 'text-info' },
  warning: { border: 'border-l-warning', bg: 'bg-warning/5', icon: 'text-warning' },
  tip:     { border: 'border-l-success', bg: 'bg-success/5', icon: 'text-success' },
  danger:  { border: 'border-l-destructive', bg: 'bg-destructive/5', icon: 'text-destructive' },
};

function CalloutNodeView({ node, updateAttributes }: any) {
  const type = node.attrs.type as string;
  const styles = CALLOUT_STYLES[type] || CALLOUT_STYLES.note;

  const cycleType = () => {
    const types = Object.keys(CALLOUT_STYLES);
    const next = types[(types.indexOf(type) + 1) % types.length];
    updateAttributes({ type: next });
  };

  return (
    <NodeViewWrapper className={`my-2 flex items-start gap-2 rounded-md border-l-3 ${styles.border} ${styles.bg} px-3 py-2`}>
      <button
        type="button"
        contentEditable={false}
        onClick={cycleType}
        className={`mt-0.5 flex-shrink-0 cursor-pointer rounded p-0.5 transition-colors hover:bg-foreground/10 ${styles.icon}`}
        title={`${type} — click to change type`}
      >
        <MessageSquareText className="h-4 w-4" />
      </button>
      <NodeViewContent className="flex-1 text-sm leading-[1.7] outline-none" />
    </NodeViewWrapper>
  );
}
