import { BookOpen, FileText, MessageSquare, RotateCcw, Trash2, Clock } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { TrashItem } from './types';

interface TrashCardProps {
  item: TrashItem;
  selected: boolean;
  onToggle: () => void;
  onRestore: () => void;
  onPurge: () => void;
  disabled?: boolean;
}

function daysLeft(deletedAt: string): number {
  const deleted = new Date(deletedAt).getTime();
  const expiry = deleted + 30 * 24 * 60 * 60 * 1000;
  return Math.max(0, Math.ceil((expiry - Date.now()) / (24 * 60 * 60 * 1000)));
}

function relativeDeleted(iso: string): string {
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / (24 * 60 * 60 * 1000));
  if (days === 0) return 'Deleted today';
  if (days === 1) return 'Deleted yesterday';
  return `Deleted ${days} days ago`;
}

const TYPE_ICON: Record<string, { icon: React.ReactNode; bg: string; fg: string }> = {
  book:    { icon: <BookOpen className="h-[18px] w-[18px]" />,       bg: 'bg-primary/10',    fg: 'text-primary' },
  chapter: { icon: <FileText className="h-[18px] w-[18px]" />,      bg: 'bg-accent/10',     fg: 'text-accent-foreground' },
  chat:    { icon: <MessageSquare className="h-[18px] w-[18px]" />, bg: 'bg-info/10',       fg: 'text-info' },
};

export function TrashCard({ item, selected, onToggle, onRestore, onPurge, disabled }: TrashCardProps) {
  const remaining = daysLeft(item.deletedAt);
  const urgent = remaining <= 7;

  return (
    <div
      className={cn(
        'flex items-center gap-3 rounded-lg border px-4 py-3.5 transition-colors',
        selected
          ? 'border-ring bg-ring/5'
          : 'border-border bg-card hover:border-border-hover hover:bg-card-hover',
      )}
    >
      <input
        type="checkbox"
        checked={selected}
        onChange={onToggle}
        className="h-4 w-4 shrink-0 cursor-pointer rounded border-border bg-input accent-primary"
      />

      {item.type === 'glossary' && item.iconColor ? (
        <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: item.iconColor }} />
      ) : (() => {
        const style = TYPE_ICON[item.type] ?? TYPE_ICON.book;
        return (
          <div className={cn('flex h-9 w-9 shrink-0 items-center justify-center rounded-md', style.bg, style.fg)}>
            {style.icon}
          </div>
        );
      })()}

      <div className="min-w-0 flex-1">
        {/* Row 1: title + badge */}
        <div className="flex items-center gap-2">
          <p className="truncate text-[13px] font-medium text-foreground">{item.title}</p>
          <span className="shrink-0 rounded-full bg-secondary px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
            {item.badge}
          </span>
        </div>
        {/* Row 2: context + deleted time — always visible */}
        <div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-muted-foreground">
          {item.context && (
            <>
              <span className="font-medium text-foreground/70">{item.context}</span>
              <span className="opacity-40">·</span>
            </>
          )}
          <span>{relativeDeleted(item.deletedAt)}</span>
        </div>
      </div>

      <span
        className={cn(
          'shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium inline-flex',
          urgent ? 'bg-destructive/15 text-destructive' : 'bg-destructive/10 text-destructive/80',
        )}
      >
        <Clock className="h-2.5 w-2.5" />
        {remaining}d left
      </span>

      <div className="flex shrink-0 gap-1">
        <button
          type="button"
          onClick={onRestore}
          disabled={disabled}
          className="flex h-7 items-center gap-1.5 rounded-md border border-border bg-transparent px-2.5 text-xs font-medium text-foreground transition-colors hover:bg-secondary disabled:opacity-50"
        >
          <RotateCcw className="h-3 w-3" />
          Restore
        </button>
        <button
          type="button"
          onClick={onPurge}
          disabled={disabled}
          title="Delete permanently"
          className="flex h-7 w-7 items-center justify-center rounded-md text-destructive transition-colors hover:bg-destructive/10 disabled:opacity-50"
        >
          <Trash2 className="h-3 w-3" />
        </button>
      </div>
    </div>
  );
}
