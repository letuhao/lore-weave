import type { JSONContent } from '@tiptap/react';
import { InlineRenderer } from '../InlineRenderer';

interface CalloutBlockProps {
  node: JSONContent;
}

const CALLOUT_TYPE_LABELS: Record<string, string> = {
  note: 'Note',
  warning: 'Warning',
  tip: 'Tip',
  danger: 'Danger',
};

export function CalloutBlock({ node }: CalloutBlockProps) {
  const type = (node.attrs?.type as string) || 'note';
  const label = CALLOUT_TYPE_LABELS[type] ?? type;

  return (
    <div className={`block-callout callout-${type}`}>
      <div className="block-callout-label">{label}</div>
      {node.content?.map((child, i) => {
        if (child.type === 'paragraph') {
          return (
            <p key={i}>
              <InlineRenderer content={child.content} />
            </p>
          );
        }
        return null;
      })}
    </div>
  );
}
