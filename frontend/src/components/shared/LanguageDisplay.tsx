import { getLanguageName } from '@/lib/languages';
import { cn } from '@/lib/utils';

interface LanguageDisplayProps {
  code: string;
  /** 'inline' = "日本語 (ja)", 'stacked' = two lines for tight spaces */
  variant?: 'inline' | 'stacked';
  className?: string;
}

export function LanguageDisplay({ code, variant = 'inline', className }: LanguageDisplayProps) {
  const name = getLanguageName(code);

  if (variant === 'stacked') {
    return (
      <span className={cn('text-center', className)}>
        <span className="block text-xs">{name}</span>
        <span className="block font-mono text-[9px] opacity-60">({code})</span>
      </span>
    );
  }

  return (
    <span className={cn('text-xs', className)}>
      {name} <span className="font-mono opacity-60">({code})</span>
    </span>
  );
}
