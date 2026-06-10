import type { JSONContent } from '@tiptap/react';
import { CitationChip, type CitationAttrs } from './CitationChip';

interface InlineRendererProps {
  content?: JSONContent[];
}

/** Wrap text in the appropriate HTML element for a single mark. */
function wrapMark(children: React.ReactNode, mark: { type: string; attrs?: Record<string, any> }): React.ReactNode {
  switch (mark.type) {
    case 'citation':
      // wiki-llm M7a — the interactive trust chip around the cited text. In the
      // body the mapper also emits a `superscript` mark, which wraps this chip in
      // <sup> (a superscript chip); the References list has no superscript, so
      // the chip there renders full-size with its "[n] label" text intact.
      return <CitationChip attrs={(mark.attrs ?? {}) as CitationAttrs}>{children}</CitationChip>;
    case 'bold':
      return <strong>{children}</strong>;
    case 'italic':
      return <em>{children}</em>;
    case 'strike':
      return <s>{children}</s>;
    case 'underline':
      return <u>{children}</u>;
    case 'code':
      return <code className="inline-code">{children}</code>;
    case 'link':
      return (
        <a
          href={mark.attrs?.href as string}
          target={mark.attrs?.target ?? '_blank'}
          rel="noopener noreferrer"
          className="inline-link"
        >
          {children}
        </a>
      );
    case 'highlight':
      return <mark className="inline-highlight">{children}</mark>;
    case 'subscript':
      return <sub>{children}</sub>;
    case 'superscript':
      return <sup>{children}</sup>;
    default:
      return children;
  }
}

/** Render a single inline node (text or hardBreak). */
function renderNode(node: JSONContent, index: number): React.ReactNode {
  if (node.type === 'hardBreak') {
    return <br key={index} />;
  }

  if (node.type === 'text') {
    let rendered: React.ReactNode = node.text ?? '';
    const marks = node.marks ?? [];
    for (const mark of marks) {
      rendered = wrapMark(rendered, mark);
    }
    return <span key={index}>{rendered}</span>;
  }

  // Unknown inline node — render nothing rather than crash
  return null;
}

/**
 * Renders Tiptap inline content (text nodes with marks + hard breaks).
 * Used by block display components (ParagraphBlock, HeadingBlock, etc.)
 * to render their inner content.
 *
 * Handles marks: bold, italic, strike, underline, code, link,
 * highlight, subscript, superscript.
 */
export function InlineRenderer({ content }: InlineRendererProps) {
  if (!content || content.length === 0) return null;
  return <>{content.map((node, i) => renderNode(node, i))}</>;
}
