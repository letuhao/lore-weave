import { RefreshCw } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import rehypeHighlight from 'rehype-highlight';
import { Button } from '@/components/ui/button';

interface AssistantMessageProps {
  content: string;
  isStreaming?: boolean;
  onRegenerate?: () => void;
  disabled?: boolean;
}

export function AssistantMessage({ content, isStreaming, onRegenerate, disabled }: AssistantMessageProps) {
  return (
    <div className="group relative">
      <div className="prose prose-sm dark:prose-invert max-w-none break-words">
        <ReactMarkdown rehypePlugins={[rehypeHighlight]}>{content}</ReactMarkdown>
        {isStreaming && (
          <span className="inline-block h-3.5 w-1.5 animate-pulse rounded-sm bg-current opacity-70" />
        )}
      </div>
      {onRegenerate && !isStreaming && !disabled && (
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="absolute -bottom-1 -left-1 h-5 w-5 p-0 opacity-0 transition-opacity group-hover:opacity-70 hover:!opacity-100"
          onClick={onRegenerate}
          title="Regenerate response"
        >
          <RefreshCw className="h-3 w-3" />
        </Button>
      )}
    </div>
  );
}
