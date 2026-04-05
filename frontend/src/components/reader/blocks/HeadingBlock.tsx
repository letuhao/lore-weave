import type { JSONContent } from '@tiptap/react';
import { InlineRenderer } from '../InlineRenderer';

interface HeadingBlockProps {
  node: JSONContent;
}

export function HeadingBlock({ node }: HeadingBlockProps) {
  const level = (node.attrs?.level as number) ?? 2;
  const Tag = `h${Math.min(Math.max(level, 1), 3)}` as 'h1' | 'h2' | 'h3';

  return (
    <Tag className={`block-heading block-heading-${level}`}>
      <InlineRenderer content={node.content} />
    </Tag>
  );
}
