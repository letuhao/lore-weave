import { useState } from 'react';
import { Check, Code2, Copy, Download, FileText } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useOutputActions } from '../hooks/useOutputActions';
import type { ChatOutput } from '../types';

const TYPE_ICON: Record<string, React.ReactNode> = {
  text: <FileText className="h-3.5 w-3.5" />,
  code: <Code2 className="h-3.5 w-3.5" />,
};

interface OutputCardProps {
  output: ChatOutput;
}

export function OutputCard({ output }: OutputCardProps) {
  const { copyToClipboard, downloadOutput } = useOutputActions();
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    await copyToClipboard(output);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  const icon = TYPE_ICON[output.output_type] ?? <FileText className="h-3.5 w-3.5" />;
  const label = output.title ?? (output.output_type === 'code' ? `Code (${output.language ?? '?'})` : 'Text');

  return (
    <div className="mt-2 rounded-md border bg-muted/30 text-xs">
      <div className="flex items-center gap-1.5 border-b px-3 py-1.5">
        <span className="text-muted-foreground">{icon}</span>
        <span className="font-medium">{label}</span>
        {output.language && (
          <span className="ml-1 rounded bg-muted px-1 py-0.5 font-mono text-[10px] text-muted-foreground">
            {output.language}
          </span>
        )}
        <div className="ml-auto flex items-center gap-1">
          <Button
            size="sm"
            variant="ghost"
            className="h-5 gap-1 px-1.5 text-[10px]"
            onClick={handleCopy}
          >
            {copied ? <Check className="h-3 w-3 text-emerald-500" /> : <Copy className="h-3 w-3" />}
            {copied ? 'Copied' : 'Copy'}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="h-5 gap-1 px-1.5 text-[10px]"
            onClick={() => downloadOutput(output)}
          >
            <Download className="h-3 w-3" />
            Save
          </Button>
        </div>
      </div>
      {output.content_text && (
        <pre className="max-h-48 overflow-auto px-3 py-2 font-mono text-[11px] leading-relaxed whitespace-pre-wrap">
          {output.content_text.length > 800
            ? output.content_text.slice(0, 800) + '\n…'
            : output.content_text}
        </pre>
      )}
    </div>
  );
}
