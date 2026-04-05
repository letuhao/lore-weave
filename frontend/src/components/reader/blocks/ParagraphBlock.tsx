import type { JSONContent } from '@tiptap/react';
import { InlineRenderer } from '../InlineRenderer';

interface ParagraphBlockProps {
  node: JSONContent;
}

export function ParagraphBlock({ node }: ParagraphBlockProps) {
  return (
    <p className="block-paragraph">
      <InlineRenderer content={node.content} />
    </p>
  );
}
