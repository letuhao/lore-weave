import type { JSONContent } from '@tiptap/react';
import { InlineRenderer } from '../InlineRenderer';

interface BlockquoteBlockProps {
  node: JSONContent;
}

export function BlockquoteBlock({ node }: BlockquoteBlockProps) {
  return (
    <blockquote className="block-blockquote">
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
    </blockquote>
  );
}
