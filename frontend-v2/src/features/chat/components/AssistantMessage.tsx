import { Copy, RefreshCw } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import rehypeHighlight from 'rehype-highlight';
import { toast } from 'sonner';

interface AssistantMessageProps {
  content: string;
  isStreaming?: boolean;
  onRegenerate?: () => void;
  disabled?: boolean;
}

export function AssistantMessage({ content, isStreaming, onRegenerate, disabled }: AssistantMessageProps) {
  async function handleCopy() {
    await navigator.clipboard.writeText(content);
    toast.success('Copied to clipboard');
  }

  return (
    <div className="group relative">
      <div className="prose prose-sm prose-invert max-w-none break-words [&_strong]:text-amber-400 [&_li]:text-foreground/90 [&_p]:text-foreground/90">
        <ReactMarkdown rehypePlugins={[rehypeHighlight]}>{content}</ReactMarkdown>
        {isStreaming && (
          <span className="inline-block h-4 w-1.5 animate-pulse rounded-sm bg-accent opacity-80" />
        )}
      </div>

      {/* Action buttons — show on hover, hide during streaming */}
      {!isStreaming && !disabled && (
        <div className="mt-1.5 flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
          <button
            type="button"
            onClick={handleCopy}
            title="Copy"
            className="rounded p-1 text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
          >
            <Copy className="h-3.5 w-3.5" />
          </button>
          {onRegenerate && (
            <button
              type="button"
              onClick={onRegenerate}
              title="Regenerate"
              className="rounded p-1 text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
            >
              <RefreshCw className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      )}
    </div>
  );
}
