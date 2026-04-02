import { BookOpen, FileText, RotateCcw, Trash2, Clock } from 'lucide-react';
import { Button } from '@/components/ui/button';
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

/** Days remaining until permanent deletion (30-day policy) */
function daysLeft(deletedAt: string): number {
  const deleted = new Date(deletedAt).getTime();
  const expiry = deleted + 30 * 24 * 60 * 60 * 1000;
  const remaining = Math.ceil((expiry - Date.now()) / (24 * 60 * 60 * 1000));
  return Math.max(0, remaining);
}

function relativeDeleted(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const days = Math.floor(diff / (24 * 60 * 60 * 1000));
  if (days === 0) return 'Deleted today';
  if (days === 1) return 'Deleted yesterday';
  return `Deleted ${days} days ago`;
}

const TYPE_ICON: Record<string, React.ReactNode> = {
  book: <BookOpen className="h-[18px] w-[18px]" />,
  glossary: null, // uses kind dot instead
  chapter: <FileText className="h-[18px] w-[18px]" />,
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
          : 'border-border bg-card hover:border-border/80 hover:bg-card/80',
      )}
    >
      {/* Checkbox */}
      <input
        type="checkbox"
        checked={selected}
        onChange={onToggle}
        className="h-4 w-4 shrink-0 cursor-pointer rounded border-border bg-input accent-primary"
      />

      {/* Icon */}
      {item.type === 'glossary' && item.iconColor ? (
        <span
          className="h-2.5 w-2.5 shrink-0 rounded-full"
          style={{ background: item.iconColor }}
        />
      ) : (
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
          {TYPE_ICON[item.type] ?? <FileText className="h-[18px] w-[18px]" />}
        </div>
      )}

      {/* Content */}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="truncate text-[13px] font-medium text-foreground">{item.title}</p>
          <span className="shrink-0 rounded-full bg-secondary px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
            {item.badge}
          </span>
          {item.context && (
            <span className="hidden text-[11px] text-muted-foreground sm:inline">
              {item.context}
            </span>
          )}
        </div>
        <p className="mt-0.5 text-[11px] text-muted-foreground">
          {relativeDeleted(item.deletedAt)}
        </p>
      </div>

      {/* Expiry badge */}
      <span
        className={cn(
          'hidden shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium sm:inline-flex',
          urgent
            ? 'bg-destructive/15 text-destructive'
            : 'bg-destructive/10 text-destructive/80',
        )}
      >
        <Clock className="h-2.5 w-2.5" />
        {remaining}d left
      </span>

      {/* Actions */}
      <div className="flex shrink-0 gap-1">
        <Button
          size="sm"
          variant="outline"
          className="h-7 gap-1.5 px-2.5 text-xs"
          onClick={onRestore}
          disabled={disabled}
        >
          <RotateCcw className="h-3 w-3" />
          Restore
        </Button>
        <Button
          size="sm"
          variant="ghost"
          className="h-7 w-7 p-0 text-destructive hover:text-destructive"
          onClick={onPurge}
          disabled={disabled}
          title="Delete permanently"
        >
          <Trash2 className="h-3 w-3" />
        </Button>
      </div>
    </div>
  );
}
