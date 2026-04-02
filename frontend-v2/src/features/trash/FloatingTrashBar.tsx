import { RotateCcw, Trash2, X } from 'lucide-react';

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
    <div className="fixed bottom-6 left-1/2 z-50 flex -translate-x-1/2 items-center gap-3 rounded-xl border border-border-hover bg-card px-5 py-2.5 shadow-[0_8px_32px_rgba(0,0,0,0.4)]">
      <span className="text-[13px] font-medium">{count} selected</span>
      <div className="h-5 w-px bg-border" />
      <button
        type="button"
        onClick={onRestore}
        disabled={disabled}
        className="flex items-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-xs font-medium text-white transition-colors hover:brightness-110 disabled:opacity-50"
      >
        <RotateCcw className="h-3 w-3" />
        Restore Selected
      </button>
      <button
        type="button"
        onClick={onPurge}
        disabled={disabled}
        className="flex items-center gap-1.5 rounded-md bg-destructive px-3 py-1.5 text-xs font-medium text-white transition-colors hover:brightness-110 disabled:opacity-50"
      >
        <Trash2 className="h-3 w-3" />
        Delete Permanently
      </button>
      <button
        type="button"
        onClick={onClear}
        title="Clear selection"
        className="flex items-center justify-center rounded-md p-1 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}
