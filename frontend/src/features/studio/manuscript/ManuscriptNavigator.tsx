// Manuscript navigator (#02) — the Side Bar's arc→chapter→scene tree.
//
// Virtualized (@tanstack/react-virtual) so a 10k-chapter book renders only the visible rows.
// Chapters page in via cursor; a Work's arcs/scenes lazy-load on expand. Selecting a chapter/
// scene calls onSelect — the dock wiring lands with #03 (Debt #1); until then it highlights.
//
// Jump v1: a client-side filter over the LOADED rows (+ chapter number). Full server search
// over all 10k is Debt #2 (the shared `useManuscriptJump` / GET …/manuscript/jump backend that
// #06a Quick Open will also use — deliberately NOT a second query path).
import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useVirtualizer } from '@tanstack/react-virtual';
import { ChevronRight, Loader2, Search } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useManuscriptTree } from './useManuscriptTree';
import type { ManuscriptNode } from './types';

interface Props {
  bookId: string;
  token: string | null;
  /** The currently selected node id (highlight). */
  selectedId?: string | null;
  /** Called when a chapter/scene row is chosen. Dock wiring is #03 (Debt #1). */
  onSelect?: (node: ManuscriptNode) => void;
}

const ROW_H = 26;

function matchesFilter(node: ManuscriptNode, f: string): boolean {
  return node.title.toLowerCase().includes(f) || (node.number != null && String(node.number).includes(f));
}

export function ManuscriptNavigator({ bookId, token, selectedId, onSelect }: Props) {
  const { t } = useTranslation('studio');
  const { source, rows, total, error, toggleExpand, loadMore } = useManuscriptTree(bookId, token);
  const [filter, setFilter] = useState('');
  const parentRef = useRef<HTMLDivElement>(null);

  // When filtering, show only loaded node rows (drop the paging `more` rows) so a filter never
  // auto-pages the whole 10k book — client filter is honestly "loaded so far" (Debt #2).
  const visible = useMemo(() => {
    const f = filter.trim().toLowerCase();
    if (!f) return rows;
    return rows.filter((r) => r.type === 'node' && matchesFilter(r.node, f));
  }, [rows, filter]);

  const virtualizer = useVirtualizer({
    count: visible.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ROW_H,
    overscan: 12,
  });
  const vItems = virtualizer.getVirtualItems();

  // Infinite paging: when a `more` row is rendered, fetch its next page (guarded in the hook so
  // it never double-fetches). Only fires when NOT filtering (filter drops `more` rows).
  useEffect(() => {
    for (const vi of vItems) {
      const row = visible[vi.index];
      if (row?.type === 'more') loadMore(row.parentKey, row.parentNodeId);
    }
  }, [vItems, visible, loadMore]);

  if (source === 'pending') {
    return <div data-testid="manuscript-nav" className="flex flex-1 items-center justify-center p-4 text-[11px] text-muted-foreground">
      <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />{t('manuscript.loading', { defaultValue: 'Loading…' })}
    </div>;
  }

  return (
    <div data-testid="manuscript-nav" className="flex min-h-0 flex-1 flex-col">
      {/* Jump / filter box */}
      <div className="flex-shrink-0 border-b p-2">
        <div className="flex h-7 items-center gap-1.5 rounded-md border bg-background px-2 text-xs text-muted-foreground">
          <Search className="h-3 w-3" />
          <input
            data-testid="manuscript-filter"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder={t('manuscript.filter', { defaultValue: 'Jump to chapter / scene…' })}
            className="min-w-0 flex-1 bg-transparent text-foreground outline-none placeholder:text-muted-foreground/60"
          />
        </div>
      </div>

      {error && <div className="px-3 py-1.5 text-[11px] text-amber-600">{error}</div>}

      <div ref={parentRef} data-testid="manuscript-scroll" className="min-h-0 flex-1 overflow-y-auto">
        {visible.length === 0 && !error ? (
          <div className="p-4 text-center text-[11px] text-muted-foreground">
            {filter
              ? t('manuscript.noMatch', { defaultValue: 'No loaded chapters match.' })
              : t('manuscript.empty', { defaultValue: 'No chapters yet.' })}
          </div>
        ) : (
          <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
            {vItems.map((vi) => {
              const row = visible[vi.index];
              const style: React.CSSProperties = {
                position: 'absolute', top: 0, left: 0, right: 0, height: ROW_H,
                transform: `translateY(${vi.start}px)`,
              };
              if (row.type === 'more') {
                return (
                  <button
                    key={`more-${row.parentKey}`}
                    type="button"
                    data-testid="manuscript-more"
                    onClick={() => loadMore(row.parentKey, row.parentNodeId)}
                    style={{ ...style, paddingLeft: 8 + row.depth * 16 }}
                    className="flex items-center gap-1.5 text-[11px] text-muted-foreground hover:text-foreground"
                  >
                    <Loader2 className="h-3 w-3 animate-spin" />
                    {t('manuscript.loadingMore', { defaultValue: 'Loading more…' })}
                  </button>
                );
              }
              const { node, depth, expanded, loading } = row;
              const selected = selectedId === node.id;
              return (
                <div
                  key={node.id}
                  data-testid={`manuscript-row-${node.id}`}
                  role="treeitem"
                  aria-expanded={node.hasChildren ? expanded : undefined}
                  aria-selected={selected}
                  onClick={() => (node.kind === 'arc' ? toggleExpand(node.id) : onSelect?.(node))}
                  style={{ ...style, paddingLeft: 4 + depth * 16 }}
                  className={cn(
                    'flex cursor-pointer items-center gap-1 pr-2 text-xs',
                    selected ? 'bg-primary/10 text-primary' : 'hover:bg-secondary',
                    node.kind === 'arc' && 'font-semibold text-accent-foreground',
                    node.kind === 'chapter' && 'font-medium',
                    node.kind === 'scene' && 'text-muted-foreground',
                  )}
                >
                  {node.hasChildren ? (
                    <button
                      type="button"
                      data-testid={`manuscript-caret-${node.id}`}
                      onClick={(e) => { e.stopPropagation(); toggleExpand(node.id); }}
                      className="flex h-4 w-4 flex-shrink-0 items-center justify-center text-muted-foreground"
                      aria-label={expanded ? 'collapse' : 'expand'}
                    >
                      {loading
                        ? <Loader2 className="h-3 w-3 animate-spin" />
                        : <ChevronRight className={cn('h-3 w-3 transition-transform', expanded && 'rotate-90')} />}
                    </button>
                  ) : (
                    <span className="flex h-4 w-4 flex-shrink-0 items-center justify-center">
                      {node.kind === 'scene' && (
                        <span className={cn('h-1.5 w-1.5 rounded-full', node.status === 'done' ? 'bg-success' : 'bg-border')} />
                      )}
                    </span>
                  )}
                  {node.number != null && (
                    <span className="w-8 flex-shrink-0 text-right font-mono text-[10px] text-muted-foreground/60">
                      {node.number}
                    </span>
                  )}
                  <span className="truncate">{node.title}</span>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="flex h-6 flex-shrink-0 items-center gap-2 border-t px-3 text-[10px] text-muted-foreground">
        {total != null && <span>{t('manuscript.count', { defaultValue: '{{n}} chapters', n: total })}</span>}
      </div>
    </div>
  );
}
