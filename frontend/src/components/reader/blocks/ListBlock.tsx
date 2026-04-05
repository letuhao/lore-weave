import type { JSONContent } from '@tiptap/react';
import { InlineRenderer } from '../InlineRenderer';

interface ListBlockProps {
  node: JSONContent;
}

/** Render a single listItem's children (paragraphs + nested lists). */
function ListItemContent({ nodes }: { nodes?: JSONContent[] }) {
  if (!nodes) return null;
  return (
    <>
      {nodes.map((child, i) => {
        if (child.type === 'paragraph') {
          return (
            <span key={i}>
              <InlineRenderer content={child.content} />
            </span>
          );
        }
        if (child.type === 'bulletList' || child.type === 'orderedList') {
          return <ListBlock key={i} node={child} />;
        }
        return null;
      })}
    </>
  );
}

export function ListBlock({ node }: ListBlockProps) {
  const Tag = node.type === 'orderedList' ? 'ol' : 'ul';
  const className = `block-list ${node.type === 'orderedList' ? 'ordered' : 'unordered'}`;

  return (
    <Tag className={className}>
      {node.content?.map((item, i) => {
        if (item.type === 'listItem') {
          return (
            <li key={i}>
              <ListItemContent nodes={item.content} />
            </li>
          );
        }
        return null;
      })}
    </Tag>
  );
}
