import ReactMarkdown from 'react-markdown';
import rehypeHighlight from 'rehype-highlight';

interface AssistantMessageProps {
  content: string;
  isStreaming?: boolean;
}

export function AssistantMessage({ content, isStreaming }: AssistantMessageProps) {
  return (
    <div className="prose prose-sm dark:prose-invert max-w-none break-words">
      <ReactMarkdown rehypePlugins={[rehypeHighlight]}>{content}</ReactMarkdown>
      {isStreaming && (
        <span className="inline-block h-3.5 w-1.5 animate-pulse rounded-sm bg-current opacity-70" />
      )}
    </div>
  );
}
