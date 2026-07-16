// M1 (mobile) view — the Journal timeline sheet: the distilled diary entries, newest-first.
// Binds the thin useDiaryEntries controller (reuses assistantApi.listDiaryEntries). Tapping an
// entry expands its distilled prose inline. DF7 / D17 (draft screen 6 "Read it, correct it — never
// share it"): the pencil opens an inline editor over the day's prose — Save calls the correct hook
// (amends the SSOT + reconciles the memory). View + local edit/expand state only (per-device UI, no
// server write of its own) — all data + correction logic lives in the hooks.
import { useState } from 'react';
import { ChevronDown, ChevronRight, BookmarkCheck, Pencil, Lock } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Sheet } from '@/components/shared/Sheet';
import type { DiaryEntry, CorrectResult } from '../../types';

export const JOURNAL_SHEET_ID = 'journal';

export interface MobileJournalSheetProps {
  entries: DiaryEntry[];
  loading: boolean;
  error: string | null;
  // D17 — correct a day's entry (null result = the call failed and was toasted; keep the editor open).
  onCorrect?: (chapterId: string, body: string, title?: string) => Promise<CorrectResult | null>;
  correctingId?: string | null;
}

export function MobileJournalSheet({ entries, loading, error, onCorrect, correctingId }: MobileJournalSheetProps) {
  const [openId, setOpenId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState('');

  const startEdit = (entry: DiaryEntry) => {
    setOpenId(entry.chapter_id);
    setEditingId(entry.chapter_id);
    setDraft(entry.body);
  };

  const saveEdit = async (entry: DiaryEntry) => {
    if (!onCorrect) return;
    const res = await onCorrect(entry.chapter_id, draft, entry.title);
    if (res?.amended) setEditingId(null); // parent refetches; failure keeps the editor open (toasted)
  };

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
          const editing = editingId === entry.chapter_id;
          const saving = correctingId === entry.chapter_id;
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

              {open && !editing && (
                <div className="border-t border-border px-3 py-2">
                  <div
                    className="text-sm leading-relaxed text-foreground/90"
                    data-testid={`journal-body-${entry.chapter_id}`}
                  >
                    {entry.body.split(/\r?\n/).map((para, i) => (
                      <p key={i} className={i > 0 ? 'mt-2' : undefined}>
                        {para}
                      </p>
                    ))}
                  </div>
                  {onCorrect && (
                    <button
                      type="button"
                      data-testid={`journal-correct-${entry.chapter_id}`}
                      onClick={() => startEdit(entry)}
                      className="mt-3 flex min-h-[44px] items-center gap-2 text-sm font-medium text-primary"
                    >
                      <Pencil className="h-4 w-4" aria-hidden="true" />
                      Correct this entry
                    </button>
                  )}
                </div>
              )}

              {open && editing && (
                <div className="border-t border-border px-3 py-2" data-testid={`journal-edit-${entry.chapter_id}`}>
                  <textarea
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    aria-label="Correct this entry"
                    data-testid={`journal-editor-${entry.chapter_id}`}
                    rows={8}
                    className="w-full resize-y rounded-md border border-border bg-background p-2 text-sm leading-relaxed outline-none focus:border-primary"
                  />
                  <div className="mt-1.5 flex items-center gap-1.5 text-[11px] text-muted-foreground">
                    <Lock className="h-3 w-3" aria-hidden="true" />
                    Correcting replaces the old memory. Never shared — only you.
                  </div>
                  <div className="mt-2 flex items-center gap-2">
                    <button
                      type="button"
                      data-testid={`journal-save-${entry.chapter_id}`}
                      disabled={saving || !draft.trim()}
                      onClick={() => void saveEdit(entry)}
                      className={cn(
                        'flex min-h-[44px] flex-1 items-center justify-center rounded-md px-3 text-sm font-medium',
                        'bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50',
                      )}
                    >
                      {saving ? 'Saving…' : 'Save correction'}
                    </button>
                    <button
                      type="button"
                      data-testid={`journal-cancel-${entry.chapter_id}`}
                      disabled={saving}
                      onClick={() => setEditingId(null)}
                      className="flex min-h-[44px] items-center justify-center rounded-md border border-border px-4 text-sm disabled:opacity-50"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </Sheet>
  );
}
