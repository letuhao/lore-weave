import { ChevronLeft, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface PagerLabels {
  /** Label before the jump input, e.g. "Page" / "Trang". */
  page?: string;
  /** Accessible label for the previous-page button. */
  prev?: string;
  /** Accessible label for the next-page button. */
  next?: string;
}

interface PagerProps {
  /** Current page, 0-based. */
  page: number;
  pageCount: number;
  /** Called with a 0-based target page; the handler/hook is expected to clamp. */
  onPageChange: (page: number) => void;
  labels?: PagerLabels;
  className?: string;
}

/**
 * Page-through pagination control: ◂ | Page [n] / N | ▸ with a direct jump
 * input. Presentational + fully controlled — pair with usePagedList for state.
 * Renders nothing for a single page. Shared by the chapter import review and the
 * translator wizard.
 */
export function Pager({ page, pageCount, onPageChange, labels, className }: PagerProps) {
  if (pageCount <= 1) return null;
  const L = { page: 'Page', prev: 'Previous page', next: 'Next page', ...labels };

  return (
    <div className={cn('flex items-center gap-1.5 text-[11px] text-muted-foreground', className)}>
      <button
        type="button"
        onClick={() => onPageChange(page - 1)}
        disabled={page === 0}
        aria-label={L.prev}
        className="rounded-md border p-1 hover:bg-secondary disabled:opacity-40 disabled:cursor-not-allowed"
      >
        <ChevronLeft className="h-3.5 w-3.5" />
      </button>
      <span className="inline-flex items-center gap-1">
        {L.page}
        <input
          type="number"
          min={1}
          max={pageCount}
          value={page + 1}
          onChange={(e) => {
            const n = Number(e.target.value);
            if (Number.isFinite(n)) onPageChange(n - 1);
          }}
          aria-label={L.page}
          className="h-6 w-12 rounded-md border bg-background px-1 text-center text-[11px] focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
        />
        / {pageCount}
      </span>
      <button
        type="button"
        onClick={() => onPageChange(page + 1)}
        disabled={page >= pageCount - 1}
        aria-label={L.next}
        className="rounded-md border p-1 hover:bg-secondary disabled:opacity-40 disabled:cursor-not-allowed"
      >
        <ChevronRight className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}
