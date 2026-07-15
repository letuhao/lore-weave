// M1 (mobile) view — the Journal timeline sheet: the distilled diary entries, newest-first.
// Binds the thin useDiaryEntries controller (reuses assistantApi.listDiaryEntries). Tapping an
// entry expands its distilled prose inline. View + a local expand toggle only (per-device UI
// state, no server write) — all data logic is in the hook.
import { useState } from 'react';
import { ChevronDown, ChevronRight, BookmarkCheck } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Sheet } from '@/components/shared/Sheet';
import type { DiaryEntry } from '../../types';

export const JOURNAL_SHEET_ID = 'journal';

export interface MobileJournalSheetProps {
  entries: DiaryEntry[];
  loading: boolean;
  error: string | null;
}

export function MobileJournalSheet({ entries, loading, error }: MobileJournalSheetProps) {
  const [openId, setOpenId] = useState<string | null>(null);

  return (
    <Sheet id={JOURNAL_SHEET_ID} title="Journal" description="Your distilled diary, newest first.">
      <div className="flex flex-col gap-2" data-testid="mobile-journal-list">
        {loading && entries.length === 0 && (
          <p className="py-6 text-center text-sm text-muted-foreground">Loading your journal…</p>
        )}
        {error && <p className="py-4 text-center text-sm text-destructive">{error}</p>}
        {!loading && !error && entries.length === 0 && (
          <p className="py-6 text-center text-sm text-muted-foreground">
            No entries yet. End a day to write your first one.
          </p>
        )}

        {entries.map((entry) => {
          const open = openId === entry.chapter_id;
          return (
            <div key={entry.chapter_id} className="rounded-lg border border-border bg-card">
              <button
                type="button"
                data-testid={`journal-entry-${entry.chapter_id}`}
                aria-expanded={open}
                onClick={() => setOpenId(open ? null : entry.chapter_id)}
                className="flex min-h-[44px] w-full items-center gap-2 px-3 py-2 text-left"
              >
                {open ? (
                  <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                ) : (
                  <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                )}
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">
                    {entry.title || entry.entry_date}
                  </span>
                  <span className="block text-xs text-muted-foreground">
                    {entry.entry_date} · {entry.word_count} words
                  </span>
                </span>
                {entry.kept && (
                  <BookmarkCheck className="h-4 w-4 shrink-0 text-emerald-500" aria-label="Kept" />
                )}
              </button>
              {open && (
                <div
                  className={cn('border-t border-border px-3 py-2 text-sm leading-relaxed text-foreground/90')}
                  data-testid={`journal-body-${entry.chapter_id}`}
                >
                  {entry.body.split(/\r?\n/).map((para, i) => (
                    <p key={i} className={i > 0 ? 'mt-2' : undefined}>
                      {para}
                    </p>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </Sheet>
  );
}
