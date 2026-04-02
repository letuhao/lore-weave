import { RotateCcw, Trash2, X } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface FloatingTrashBarProps {
  count: number;
  onRestore: () => void;
  onPurge: () => void;
  onClear: () => void;
  disabled?: boolean;
}

export function FloatingTrashBar({ count, onRestore, onPurge, onClear, disabled }: FloatingTrashBarProps) {
  if (count === 0) return null;

  return (
    <div className="fixed bottom-6 left-1/2 z-50 flex -translate-x-1/2 items-center gap-3 rounded-xl border border-border bg-card px-5 py-2.5 shadow-[0_8px_32px_rgba(0,0,0,0.4)]">
      <span className="text-[13px] font-medium text-foreground">
        {count} selected
      </span>

      <div className="h-5 w-px bg-border" />

      <Button
        size="sm"
        className="h-7 gap-1.5 bg-accent text-accent-foreground hover:bg-accent/90"
        onClick={onRestore}
        disabled={disabled}
      >
        <RotateCcw className="h-3 w-3" />
        Restore Selected
      </Button>

      <Button
        size="sm"
        variant="destructive"
        className="h-7 gap-1.5"
        onClick={onPurge}
        disabled={disabled}
      >
        <Trash2 className="h-3 w-3" />
        Delete Permanently
      </Button>

      <Button
        size="sm"
        variant="ghost"
        className="h-7 w-7 p-0 text-muted-foreground"
        onClick={onClear}
        title="Clear selection"
      >
        <X className="h-3.5 w-3.5" />
      </Button>
    </div>
  );
}
