import { type ReactNode } from 'react';
import { cn } from '@/lib/utils';

interface AttrCardProps {
  name: string;
  code: string;
  fieldType: string;
  isSystem: boolean;
  isRequired: boolean;
  modified: boolean;
  children: ReactNode;
}

export function AttrCard({ name, code, fieldType, isSystem, isRequired, modified, children }: AttrCardProps) {
  return (
    <div className={cn(
      'rounded-lg border bg-card overflow-hidden transition-colors hover:border-[hsl(var(--border-hover,25_6%_24%))]',
      modified && 'border-l-[3px] border-l-warning',
    )}>
      <div className="flex items-center justify-between px-3.5 py-2.5" style={{ background: 'rgba(24,20,18,0.3)' }}>
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-semibold">{name}</span>
          {isSystem ? (
            <span className="rounded bg-info/12 px-1.5 py-0.5 text-[9px] font-semibold text-info">SYS</span>
          ) : (
            <span className="rounded bg-warning/12 px-1.5 py-0.5 text-[9px] font-semibold text-warning">USR</span>
          )}
          {isRequired && <span className="text-[10px] font-medium text-destructive">*required</span>}
          {modified && <span className="rounded bg-warning/8 px-1.5 py-0.5 text-[9px] text-warning">modified</span>}
        </div>
        <span className="font-mono text-[9px] text-muted-foreground">{code} · {fieldType}</span>
      </div>
      <div className="px-3.5 py-2.5">
        {children}
      </div>
    </div>
  );
}
