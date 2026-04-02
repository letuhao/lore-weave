import { useState } from 'react';
import { Check, ClipboardPaste, Code2, Copy, Download, FileText } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { chatApi } from '../api';
import { firePasteToEditor } from '../utils/pasteToEditor';
import type { ChatOutput } from '../types';

const TYPE_ICON: Record<string, React.ReactNode> = {
  text: <FileText className="h-3.5 w-3.5" />,
  code: <Code2 className="h-3.5 w-3.5" />,
};

interface OutputCardProps {
  output: ChatOutput;
}

export function OutputCard({ output }: OutputCardProps) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    await navigator.clipboard.writeText(output.content_text ?? '');
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  function handlePasteToEditor() {
    firePasteToEditor({
      text: output.content_text ?? '',
      language: output.language,
      sourceOutputId: output.output_id,
    });
    toast.success('Sent to editor');
  }

  function handleDownload() {
    const url = chatApi.downloadUrl(output.output_id);
    const a = document.createElement('a');
    a.href = url;
    a.download = output.file_name ?? `output-${output.output_id}.txt`;
    a.click();
  }

  const icon = TYPE_ICON[output.output_type] ?? <FileText className="h-3.5 w-3.5" />;
  const label = output.title ?? (output.output_type === 'code' ? `Code (${output.language ?? '?'})` : 'Text');

  return (
    <div className="mt-2 rounded-md border border-border bg-card/50 text-xs">
      <div className="flex items-center gap-1.5 border-b border-border px-3 py-1.5">
        <span className="text-muted-foreground">{icon}</span>
        <span className="font-medium text-foreground">{label}</span>
        {output.language && (
          <span className="ml-1 rounded bg-secondary px-1 py-0.5 font-mono text-[10px] text-muted-foreground">
            {output.language}
          </span>
        )}
        <div className="ml-auto flex items-center gap-1">
          <Button
            size="sm"
            variant="ghost"
            className="h-5 gap-1 px-1.5 text-[10px] text-muted-foreground hover:text-foreground"
            onClick={handleCopy}
          >
            {copied ? <Check className="h-3 w-3 text-emerald-500" /> : <Copy className="h-3 w-3" />}
            {copied ? 'Copied' : 'Copy'}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="h-5 gap-1 px-1.5 text-[10px] text-muted-foreground hover:text-foreground"
            onClick={handlePasteToEditor}
          >
            <ClipboardPaste className="h-3 w-3" />
            To Editor
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="h-5 gap-1 px-1.5 text-[10px] text-muted-foreground hover:text-foreground"
            onClick={handleDownload}
          >
            <Download className="h-3 w-3" />
            Save
          </Button>
        </div>
      </div>
      {output.content_text && (
        <pre className="max-h-48 overflow-auto px-3 py-2 font-mono text-[11px] leading-relaxed whitespace-pre-wrap text-foreground/80">
          {output.content_text.length > 800
            ? output.content_text.slice(0, 800) + '\n\u2026'
            : output.content_text}
        </pre>
      )}
    </div>
  );
}
