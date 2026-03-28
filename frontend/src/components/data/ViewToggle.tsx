import { cn } from '@/lib/utils';
import { LayoutGrid, LayoutList } from 'lucide-react';
import type { ViewMode } from './types';

interface ViewToggleProps {
  view: ViewMode;
  onViewChange: (view: ViewMode) => void;
  className?: string;
}

export function ViewToggle({ view, onViewChange, className }: ViewToggleProps) {
  return (
    <div className={cn('inline-flex rounded-md border', className)}>
      <button
        type="button"
        onClick={() => onViewChange('table')}
        className={cn(
          'flex items-center gap-1.5 rounded-l-md px-2.5 py-1.5 text-xs font-medium transition-colors',
          view === 'table'
            ? 'bg-accent text-accent-foreground'
            : 'text-muted-foreground hover:bg-muted',
        )}
        aria-label="Table view"
      >
        <LayoutList className="h-3.5 w-3.5" />
        <span className="hidden sm:inline">Table</span>
      </button>
      <button
        type="button"
        onClick={() => onViewChange('grid')}
        className={cn(
          'flex items-center gap-1.5 rounded-r-md border-l px-2.5 py-1.5 text-xs font-medium transition-colors',
          view === 'grid'
            ? 'bg-accent text-accent-foreground'
            : 'text-muted-foreground hover:bg-muted',
        )}
        aria-label="Grid view"
      >
        <LayoutGrid className="h-3.5 w-3.5" />
        <span className="hidden sm:inline">Grid</span>
      </button>
    </div>
  );
}
