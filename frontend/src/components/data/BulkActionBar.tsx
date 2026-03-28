import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { X } from 'lucide-react';
import type { ReactNode } from 'react';

interface BulkActionBarProps {
  selectedCount: number;
  onClear: () => void;
  children: ReactNode;
  className?: string;
}

export function BulkActionBar({ selectedCount, onClear, children, className }: BulkActionBarProps) {
  if (selectedCount === 0) return null;

  return (
    <div
      className={cn(
        'fixed bottom-6 left-1/2 z-30 flex -translate-x-1/2 items-center gap-3 rounded-lg border bg-background px-4 py-2.5 shadow-lg',
        className,
      )}
    >
      <span className="text-sm font-medium">
        {selectedCount} selected
      </span>
      <div className="h-4 w-px bg-border" />
      <div className="flex items-center gap-2">{children}</div>
      <Button variant="ghost" size="sm" onClick={onClear} className="ml-1 h-7 w-7 p-0">
        <X className="h-3.5 w-3.5" />
      </Button>
    </div>
  );
}
