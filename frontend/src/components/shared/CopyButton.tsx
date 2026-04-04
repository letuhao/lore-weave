import { useState } from 'react';
import { Copy, Check } from 'lucide-react';
import { cn } from '@/lib/utils';

interface CopyButtonProps {
  value: string;
  label?: string;
  className?: string;
}

export function CopyButton({ value, label, className }: CopyButtonProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <button
      onClick={() => void handleCopy()}
      className={cn(
        'inline-flex items-center gap-2 rounded-md border px-3 py-2 text-sm transition-colors hover:bg-secondary',
        copied && 'border-success/30 text-success',
        className,
      )}
    >
      {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
      {label ?? (copied ? 'Copied!' : 'Copy')}
    </button>
  );
}
