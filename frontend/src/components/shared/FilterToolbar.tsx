import { type ReactNode } from 'react';
import { Search, X } from 'lucide-react';
import { cn } from '@/lib/utils';

interface FilterToolbarProps {
  search?: string;
  onSearchChange?: (value: string) => void;
  searchPlaceholder?: string;
  filters?: ReactNode;
  activeFilters?: { label: string; onRemove: () => void }[];
  trailing?: ReactNode;
  className?: string;
}

export function FilterToolbar({
  search, onSearchChange, searchPlaceholder = 'Search...',
  filters, activeFilters, trailing, className,
}: FilterToolbarProps) {
  return (
    <div className={cn('flex flex-wrap items-center gap-3', className)}>
      {/* Search input */}
      {onSearchChange && (
        <div className="relative min-w-[200px] max-w-sm flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={search ?? ''}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder={searchPlaceholder}
            className="w-full rounded-md border bg-background py-2 pl-9 pr-3 text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-ring/40"
          />
        </div>
      )}

      {/* Filter dropdowns */}
      {filters}

      {/* Active filter chips */}
      {activeFilters && activeFilters.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {activeFilters.map((f) => (
            <span
              key={f.label}
              className="inline-flex items-center gap-1 rounded-full border border-primary bg-primary/10 px-2.5 py-0.5 text-xs font-medium text-primary"
            >
              {f.label}
              <button onClick={f.onRemove} className="rounded-full p-0.5 hover:bg-primary/20">
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Right-aligned content (counts, sort, etc.) */}
      {trailing && <div className="ml-auto">{trailing}</div>}
    </div>
  );
}
