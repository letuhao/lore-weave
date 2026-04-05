import { Copy, Check } from 'lucide-react';
import { useState, useCallback, useMemo } from 'react';
import type { JSONContent } from '@tiptap/react';

interface SourceViewProps {
  json: JSONContent;
}

/**
 * Read-only Block JSON viewer for the chapter editor.
 * Shows syntax-highlighted JSON of the Tiptap document structure.
 */
export function SourceView({ json }: SourceViewProps) {
  const [copied, setCopied] = useState(false);

  const formatted = useMemo(() => {
    // Strip _text snapshots from display (they're computed, not authored)
    const clean = {
      ...json,
      content: json.content?.map((block) => {
        const { _text, ...rest } = block as any;
        return rest;
      }),
    };
    return JSON.stringify(clean, null, 2);
  }, [json]);

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(formatted).then(
      () => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      },
      () => {},
    );
  }, [formatted]);

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between border-b bg-card px-4 py-1.5 text-[10px] text-muted-foreground">
        <span>Block JSON — read-only view of chapter structure</span>
        <button
          type="button"
          onClick={handleCopy}
          className="flex items-center gap-1 rounded px-2 py-0.5 transition-colors hover:bg-secondary hover:text-foreground"
        >
          {copied ? (
            <><Check className="h-3 w-3 text-success" /> Copied</>
          ) : (
            <><Copy className="h-3 w-3" /> Copy JSON</>
          )}
        </button>
      </div>

      {/* JSON content */}
      <pre className="flex-1 overflow-auto bg-background p-4 font-mono text-[11px] leading-relaxed text-[#c8c0b4]">
        <code>{syntaxHighlight(formatted)}</code>
      </pre>
    </div>
  );
}

/** Simple JSON syntax highlighter (no dependency) */
function syntaxHighlight(json: string): (JSX.Element | string)[] {
  const parts: (JSX.Element | string)[] = [];
  // Match JSON tokens: strings, numbers, booleans, null, keys
  const regex = /("(?:\\.|[^"\\])*")\s*:|("(?:\\.|[^"\\])*")|(-?\d+\.?\d*(?:[eE][+-]?\d+)?)|(\btrue\b|\bfalse\b)|(\bnull\b)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let idx = 0;

  while ((match = regex.exec(json)) !== null) {
    // Add text before match
    if (match.index > lastIndex) {
      parts.push(json.slice(lastIndex, match.index));
    }

    if (match[1]) {
      // Key — match[0] includes the trailing `: `, so use the full match
      parts.push(<span key={idx++} className="text-info">{match[1]}</span>);
      const afterKey = json.slice(match.index + match[1].length, regex.lastIndex);
      parts.push(afterKey);
    } else if (match[2]) {
      // String value
      parts.push(<span key={idx++} className="text-success">{match[2]}</span>);
    } else if (match[3]) {
      // Number
      parts.push(<span key={idx++} className="text-destructive">{match[3]}</span>);
    } else if (match[4]) {
      // Boolean
      parts.push(<span key={idx++} className="text-warning">{match[4]}</span>);
    } else if (match[5]) {
      // Null
      parts.push(<span key={idx++} className="text-warning">{match[5]}</span>);
    }

    lastIndex = regex.lastIndex;
  }

  // Remaining text
  if (lastIndex < json.length) {
    parts.push(json.slice(lastIndex));
  }

  return parts;
}
