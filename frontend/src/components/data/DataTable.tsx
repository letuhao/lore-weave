import { cn } from '@/lib/utils';
import { Skeleton } from '@/components/ui/skeleton';
import { ArrowUp, ArrowDown, ArrowUpDown } from 'lucide-react';
import type { ColumnDef, SortState } from './types';

/* ── Responsive hide helpers ──────────────────────────────────────────────────── */
const hideBelowClass: Record<string, string> = {
  sm: 'hidden sm:table-cell',
  md: 'hidden md:table-cell',
  lg: 'hidden lg:table-cell',
  xl: 'hidden xl:table-cell',
};

/* ── Props ────────────────────────────────────────────────────────────────────── */

interface DataTableProps<T> {
  columns: ColumnDef<T>[];
  data: T[];
  /** Unique key extractor for each row. */
  rowKey: (row: T) => string;
  /** Loading state — shows skeleton rows. */
  isLoading?: boolean;
  /** Number of skeleton rows to show when loading. */
  skeletonRows?: number;
  /** Current sort state. */
  sort?: SortState | null;
  /** Called when a sortable column header is clicked. */
  onSort?: (field: string) => void;
  /** Row selection. */
  selectedIds?: Set<string>;
  onToggleSelect?: (id: string) => void;
  onSelectAll?: () => void;
  onDeselectAll?: () => void;
  /** Callback when a row is clicked. */
  onRowClick?: (row: T) => void;
  /** ID of the currently active/highlighted row. */
  activeRowId?: string | null;
  className?: string;
}

export function DataTable<T>({
  columns,
  data,
  rowKey,
  isLoading,
  skeletonRows = 5,
  sort,
  onSort,
  selectedIds,
  onToggleSelect,
  onSelectAll,
  onDeselectAll,
  onRowClick,
  activeRowId,
  className,
}: DataTableProps<T>) {
  const hasSelection = selectedIds !== undefined && onToggleSelect;
  const allSelected = hasSelection && data.length > 0 && data.every((r) => selectedIds!.has(rowKey(r)));
  const someSelected = hasSelection && data.some((r) => selectedIds!.has(rowKey(r)));

  function handleSelectAllToggle() {
    if (allSelected) {
      onDeselectAll?.();
    } else {
      onSelectAll?.();
    }
  }

  function renderSortIcon(col: ColumnDef<T>) {
    if (!col.sortable) return null;
    if (sort?.field !== col.key) return <ArrowUpDown className="ml-1 inline h-3 w-3 opacity-40" />;
    return sort.direction === 'asc' ? (
      <ArrowUp className="ml-1 inline h-3 w-3" />
    ) : (
      <ArrowDown className="ml-1 inline h-3 w-3" />
    );
  }

  return (
    <div className={cn('overflow-x-auto rounded-md border', className)}>
      <table className="w-full text-sm">
        {/* ── Header ─────────────────────────────────────────────────────────── */}
        <thead>
          <tr className="border-b bg-muted/50">
            {hasSelection && (
              <th className="w-10 px-3 py-2.5 text-center">
                <input
                  type="checkbox"
                  checked={allSelected}
                  ref={(el) => {
                    if (el) el.indeterminate = !!(someSelected && !allSelected);
                  }}
                  onChange={handleSelectAllToggle}
                  className="h-3.5 w-3.5 rounded border-input accent-primary"
                  aria-label="Select all rows"
                />
              </th>
            )}
            {columns.map((col) => (
              <th
                key={col.key}
                className={cn(
                  'px-3 py-2.5 text-left text-xs font-medium text-muted-foreground',
                  col.sortable && 'cursor-pointer select-none hover:text-foreground',
                  col.widthClass,
                  col.hideBelow && hideBelowClass[col.hideBelow],
                )}
                onClick={() => col.sortable && onSort?.(col.key)}
              >
                <span className="inline-flex items-center">
                  {col.header}
                  {renderSortIcon(col)}
                </span>
              </th>
            ))}
          </tr>
        </thead>

        {/* ── Body ───────────────────────────────────────────────────────────── */}
        <tbody className="divide-y">
          {isLoading
            ? Array.from({ length: skeletonRows }).map((_, i) => (
                <tr key={`skeleton-${i}`}>
                  {hasSelection && (
                    <td className="px-3 py-2.5">
                      <Skeleton className="mx-auto h-3.5 w-3.5" />
                    </td>
                  )}
                  {columns.map((col) => (
                    <td
                      key={col.key}
                      className={cn(
                        'px-3 py-2.5',
                        col.hideBelow && hideBelowClass[col.hideBelow],
                      )}
                    >
                      <Skeleton className="h-4 w-3/4" />
                    </td>
                  ))}
                </tr>
              ))
            : data.map((row) => {
                const id = rowKey(row);
                const isSelected = selectedIds?.has(id);
                const isActive = activeRowId === id;

                return (
                  <tr
                    key={id}
                    onClick={() => onRowClick?.(row)}
                    className={cn(
                      'transition-colors',
                      onRowClick && 'cursor-pointer',
                      isActive && 'bg-accent/50',
                      isSelected && 'bg-primary/5',
                      !isActive && !isSelected && 'hover:bg-muted/50',
                    )}
                  >
                    {hasSelection && (
                      <td className="px-3 py-2.5 text-center">
                        <input
                          type="checkbox"
                          checked={!!isSelected}
                          onChange={(e) => {
                            e.stopPropagation();
                            onToggleSelect!(id);
                          }}
                          onClick={(e) => e.stopPropagation()}
                          className="h-3.5 w-3.5 rounded border-input accent-primary"
                          aria-label={`Select row ${id}`}
                        />
                      </td>
                    )}
                    {columns.map((col) => (
                      <td
                        key={col.key}
                        className={cn(
                          'px-3 py-2.5',
                          col.widthClass,
                          col.hideBelow && hideBelowClass[col.hideBelow],
                        )}
                      >
                        {col.render
                          ? col.render(row)
                          : String((row as Record<string, unknown>)[col.key] ?? '')}
                      </td>
                    ))}
                  </tr>
                );
              })}
        </tbody>
      </table>
    </div>
  );
}
