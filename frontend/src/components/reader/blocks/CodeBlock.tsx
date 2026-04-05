import { useCallback } from 'react';
import type { JSONContent } from '@tiptap/react';

interface CodeBlockProps {
  node: JSONContent;
}

/** Extract plain text from a codeBlock node. */
function extractCodeText(node: JSONContent): string {
  if (!node.content) return '';
  return node.content
    .map((child) => (child.type === 'text' ? child.text ?? '' : ''))
    .join('');
}

export function CodeBlock({ node }: CodeBlockProps) {
  const language = (node.attrs?.language as string) || '';
  const code = extractCodeText(node);

  const handleCopy = useCallback(() => {
    void navigator.clipboard.writeText(code);
  }, [code]);

  return (
    <div className="block-code">
      <div className="block-code-header">
        <span className="block-code-lang">{language || 'plain'}</span>
        <button type="button" className="block-code-copy" onClick={handleCopy}>
          Copy
        </button>
      </div>
      <pre>{code}</pre>
    </div>
  );
}
