import { ChevronLeft, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useTranslation } from 'react-i18next';

interface PaginationProps {
  total: number;
  limit: number;
  offset: number;
  onChange: (offset: number) => void;
  className?: string;
}

export function Pagination({ total, limit, offset, onChange, className }: PaginationProps) {
  const { t } = useTranslation();
  const currentPage = Math.floor(offset / limit) + 1;
  const totalPages = Math.max(1, Math.ceil(total / limit));
  const from = Math.min(offset + 1, total);
  const to = Math.min(offset + limit, total);

  if (total <= limit) return null;

  const goTo = (page: number) => {
    const clamped = Math.max(1, Math.min(page, totalPages));
    onChange((clamped - 1) * limit);
  };

  // Generate page numbers to show
  const pages: (number | '...')[] = [];
  if (totalPages <= 7) {
    for (let i = 1; i <= totalPages; i++) pages.push(i);
  } else {
    pages.push(1);
    if (currentPage > 3) pages.push('...');
    for (let i = Math.max(2, currentPage - 1); i <= Math.min(totalPages - 1, currentPage + 1); i++) {
      pages.push(i);
    }
    if (currentPage < totalPages - 2) pages.push('...');
    pages.push(totalPages);
  }

  return (
    <div className={cn('flex items-center justify-between text-xs text-muted-foreground', className)}>
      <span>{t('common.showing_of', { from, to, total })}</span>
      <div className="flex items-center gap-1">
        <button
          onClick={() => goTo(currentPage - 1)}
          disabled={currentPage === 1}
          className="flex h-7 w-7 items-center justify-center rounded border disabled:opacity-30"
        >
          <ChevronLeft className="h-3.5 w-3.5" />
        </button>
        {pages.map((p, i) =>
          p === '...' ? (
            <span key={`dots-${i}`} className="px-1">...</span>
          ) : (
            <button
              key={p}
              onClick={() => goTo(p)}
              className={cn(
                'flex h-7 w-7 items-center justify-center rounded border text-xs',
                p === currentPage
                  ? 'border-primary bg-primary/15 text-primary'
                  : 'hover:bg-secondary',
              )}
            >
              {p}
            </button>
          ),
        )}
        <button
          onClick={() => goTo(currentPage + 1)}
          disabled={currentPage === totalPages}
          className="flex h-7 w-7 items-center justify-center rounded border disabled:opacity-30"
        >
          <ChevronRight className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}
