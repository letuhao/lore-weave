import { useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import type { ParsedChapter } from './parseChapters';

interface Props {
  chapters: ParsedChapter[];
  onSetIncluded: (id: string, included: boolean) => void;
  onSetTitle: (id: string, title: string) => void;
  /** select-all / deselect-all over the WHOLE list (not just the page) */
  onSetAllIncluded: (included: boolean) => void;
  pageSize?: number;
}

/**
 * Paginated (page-through) review of parsed chapters before import. Built for very
 * large folders (4000+) — only the current page is rendered. Each row shows the
 * global order #, an editable title, the filename, and an include checkbox.
 */
export function ChapterImportReview({
  chapters,
  onSetIncluded,
  onSetTitle,
  onSetAllIncluded,
  pageSize = 50,
}: Props) {
  const [page, setPage] = useState(0);
  const total = chapters.length;
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const safePage = Math.min(page, pages - 1);
  const start = safePage * pageSize;
  const slice = chapters.slice(start, start + pageSize);
  const includedCount = chapters.reduce((n, c) => n + (c.included ? 1 : 0), 0);
  const allIncluded = total > 0 && includedCount === total;

  const go = (p: number) => setPage(Math.min(pages - 1, Math.max(0, p)));

  return (
    <div className="space-y-2">
      {/* Header: counts + select-all + pager */}
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-1.5 cursor-pointer">
            <input
              type="checkbox"
              checked={allIncluded}
              onChange={(e) => onSetAllIncluded(e.target.checked)}
              className="h-3.5 w-3.5 rounded border-border accent-primary"
            />
            <span className="text-muted-foreground">
              {includedCount} / {total} selected
            </span>
          </label>
        </div>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => go(safePage - 1)}
            disabled={safePage === 0}
            className="rounded border p-1 disabled:opacity-40 hover:bg-secondary"
            aria-label="Previous page"
          >
            <ChevronLeft className="h-3.5 w-3.5" />
          </button>
          <span className="text-muted-foreground">
            Page{' '}
            <input
              type="number"
              min={1}
              max={pages}
              value={safePage + 1}
              onChange={(e) => go((Number(e.target.value) || 1) - 1)}
              className="w-12 rounded border bg-background px-1 py-0.5 text-center text-[11px]"
            />{' '}
            / {pages}
          </span>
          <button
            type="button"
            onClick={() => go(safePage + 1)}
            disabled={safePage >= pages - 1}
            className="rounded border p-1 disabled:opacity-40 hover:bg-secondary"
            aria-label="Next page"
          >
            <ChevronRight className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Rows */}
      <div className="max-h-72 overflow-y-auto rounded-lg border divide-y">
        {slice.map((c, i) => (
          <div
            key={c.id}
            className={`flex items-center gap-2 px-3 py-1.5 ${c.included ? '' : 'opacity-40'}`}
          >
            <input
              type="checkbox"
              checked={c.included}
              onChange={(e) => onSetIncluded(c.id, e.target.checked)}
              aria-label={`Include ${c.filename}`}
              className="h-3.5 w-3.5 shrink-0 rounded border-border accent-primary"
            />
            <span className="w-10 shrink-0 text-right font-mono text-[10px] text-muted-foreground">
              {start + i + 1}
            </span>
            <input
              type="text"
              value={c.title}
              onChange={(e) => onSetTitle(c.id, e.target.value)}
              className="min-w-0 flex-1 rounded border border-transparent bg-transparent px-1.5 py-0.5 text-xs hover:border-border focus:border-ring focus:outline-none"
            />
            <span className="hidden shrink-0 truncate text-[10px] text-muted-foreground sm:block sm:max-w-[180px]">
              {c.filename}
            </span>
            <span className="w-14 shrink-0 text-right text-[10px] text-muted-foreground">
              {(c.size / 1024).toFixed(1)} KB
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
