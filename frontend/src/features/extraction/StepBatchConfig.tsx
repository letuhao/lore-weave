import { useEffect, useMemo, useState } from 'react';
import { Loader2, Info } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth';
import { booksApi, type Chapter } from '@/features/books/api';
import { ChapterListBrowser } from '@/components/shared/ChapterListBrowser';
import type { ContextFilters } from './types';
import { cn } from '@/lib/utils';

type SelectionMode = 'all' | 'range' | 'pick';

interface StepBatchConfigProps {
  bookId: string;
  chapterIds: string[];
  contextFilters: ContextFilters;
  maxEntitiesPerKind: number;
  onChapterIdsChange: (ids: string[]) => void;
  onContextFiltersChange: (filters: ContextFilters) => void;
  onMaxEntitiesChange: (n: number) => void;
}

export function StepBatchConfig({
  bookId,
  chapterIds,
  contextFilters,
  maxEntitiesPerKind,
  onChapterIdsChange,
  onContextFiltersChange,
  onMaxEntitiesChange,
}: StepBatchConfigProps) {
  const { t } = useTranslation('extraction');
  const { accessToken } = useAuth();
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [loading, setLoading] = useState(true);
  const [mode, setMode] = useState<SelectionMode>('all');
  const [rangeFrom, setRangeFrom] = useState(1);
  const [rangeTo, setRangeTo] = useState(1);
  // Stable Set identity for the browser's controlled selection (avoids a new Set
  // every render).
  const pickSelection = useMemo(() => new Set(chapterIds), [chapterIds]);

  // Loop-fetch the FULL chapter list (paginate, since the BE caps a page at 100):
  // the all/range modes enumerate ids client-side, so a single capped fetch
  // silently truncated 'all' / 'range' to the first 100 on big books. pick mode
  // uses the paginated <ChapterListBrowser> instead and doesn't rely on this.
  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;
    setLoading(true);
    (async () => {
      const all: Chapter[] = [];
      const fetchSize = 100;
      for (let offset = 0; ; offset += fetchSize) {
        const resp = await booksApi.listChapters(accessToken, bookId, {
          lifecycle_state: 'active', limit: fetchSize, offset,
        });
        all.push(...resp.items);
        if (resp.items.length < fetchSize || all.length >= resp.total) break;
      }
      if (cancelled) return;
      setChapters(all);
      setRangeTo(all.length);
      // Default: select all if no chapters pre-selected.
      if (chapterIds.length === 0) {
        onChapterIdsChange(all.map((c) => c.chapter_id));
      }
    })()
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [accessToken, bookId]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleModeChange = (newMode: SelectionMode) => {
    setMode(newMode);
    if (newMode === 'all') {
      onChapterIdsChange(chapters.map((c) => c.chapter_id));
    } else if (newMode === 'range') {
      applyRange(rangeFrom, rangeTo);
    }
  };

  const applyRange = (from: number, to: number) => {
    const ids = chapters.slice(from - 1, to).map((c) => c.chapter_id);
    onChapterIdsChange(ids);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {/* Chapter selection */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-xs font-medium">{t('batch.chapterSelection')}</h3>
          <div className="flex gap-1">
            {(['all', 'range', 'pick'] as const).map((m) => (
              <button
                key={m}
                onClick={() => handleModeChange(m)}
                className={cn(
                  'px-2.5 py-1 rounded text-[11px] font-medium transition-colors',
                  mode === m
                    ? 'bg-primary/10 text-primary'
                    : 'bg-secondary text-muted-foreground hover:text-foreground',
                )}
              >
                {t(`batch.${m === 'all' ? 'allChapters' : m === 'range' ? 'selectRange' : 'pickChapters'}`)}
              </button>
            ))}
          </div>
        </div>

        {/* Range inputs */}
        {mode === 'range' && (
          <div className="flex items-center gap-2 mb-2">
            <label className="text-[11px] text-muted-foreground">From</label>
            <input
              type="number"
              min={1}
              max={chapters.length}
              value={rangeFrom}
              onChange={(e) => {
                const v = Math.max(1, Math.min(chapters.length, +e.target.value));
                setRangeFrom(v);
                applyRange(v, rangeTo);
              }}
              className="w-16 h-7 rounded border bg-background px-2 text-xs text-center focus:border-ring focus:outline-none"
            />
            <label className="text-[11px] text-muted-foreground">to</label>
            <input
              type="number"
              min={1}
              max={chapters.length}
              value={rangeTo}
              onChange={(e) => {
                const v = Math.max(1, Math.min(chapters.length, +e.target.value));
                setRangeTo(v);
                applyRange(rangeFrom, v);
              }}
              className="w-16 h-7 rounded border bg-background px-2 text-xs text-center focus:border-ring focus:outline-none"
            />
            <span className="text-[11px] text-muted-foreground">of {chapters.length}</span>
          </div>
        )}

        {/* Pick mode — the shared server-paged browser (multi). Replaces the old
            in-memory list that was capped by the chapter-list limit (couldn't pick
            past the first page on a big book). Selection persists across pages. */}
        {mode === 'pick' && (
          <div className="mb-2">
            <ChapterListBrowser
              bookId={bookId}
              selectionMode="multi"
              selectedIds={pickSelection}
              onSelectionChange={(ids) => onChapterIdsChange([...ids])}
              pageSize={50}
            />
          </div>
        )}

        {mode !== 'pick' && (
          <p className="text-[11px] text-muted-foreground">
            {t('batch.chaptersSelected', { count: chapterIds.length })}
          </p>
        )}
      </div>

      {/* Context filters */}
      <div>
        <h3 className="text-xs font-medium mb-1">{t('batch.contextFilters')}</h3>
        <p className="text-[10px] text-muted-foreground mb-3">{t('batch.contextDescription')}</p>

        <div className="grid grid-cols-2 gap-4">
          {/* Frequency */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-[11px] text-muted-foreground">{t('batch.minFrequency')}</label>
              <span className="text-xs font-mono text-primary">{contextFilters.min_frequency ?? 2}</span>
            </div>
            <input
              type="range"
              min={1}
              max={20}
              value={contextFilters.min_frequency ?? 2}
              onChange={(e) =>
                onContextFiltersChange({ ...contextFilters, min_frequency: +e.target.value })
              }
              className="w-full h-1 rounded-full appearance-none bg-border accent-primary"
            />
            <div className="flex justify-between text-[9px] text-muted-foreground mt-0.5">
              <span>1 (all)</span>
              <span>20 (frequent)</span>
            </div>
          </div>

          {/* Recency */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-[11px] text-muted-foreground">{t('batch.recencyWindow')}</label>
              <span className="text-xs font-mono text-primary">{contextFilters.recency_window ?? 100}</span>
            </div>
            <input
              type="range"
              min={10}
              max={500}
              step={10}
              value={contextFilters.recency_window ?? 100}
              onChange={(e) =>
                onContextFiltersChange({ ...contextFilters, recency_window: +e.target.value })
              }
              className="w-full h-1 rounded-full appearance-none bg-border accent-primary"
            />
            <div className="flex justify-between text-[9px] text-muted-foreground mt-0.5">
              <span>10 (recent)</span>
              <span>500 (wide)</span>
            </div>
          </div>
        </div>

        {/* Max entities per kind */}
        <div className="mt-3">
          <label className="text-[11px] text-muted-foreground">{t('batch.maxEntitiesPerKind')}</label>
          <input
            type="number"
            min={5}
            max={100}
            value={maxEntitiesPerKind}
            onChange={(e) => onMaxEntitiesChange(Math.max(5, Math.min(100, +e.target.value)))}
            className="ml-2 w-16 h-7 rounded border bg-background px-2 text-xs text-center focus:border-ring focus:outline-none"
          />
        </div>

        {/* Alive filter info */}
        <div className="mt-3 flex items-start gap-2 rounded-md border bg-card/50 px-3 py-2">
          <Info className="h-3.5 w-3.5 text-primary mt-0.5 shrink-0" />
          <p className="text-[10px] text-muted-foreground">{t('batch.aliveInfo')}</p>
        </div>
      </div>
    </div>
  );
}
