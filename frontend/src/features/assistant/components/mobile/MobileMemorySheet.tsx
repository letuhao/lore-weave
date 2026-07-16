// DF6 view — "What I know" (draft screen 11) + Recall (draft screen 5): everything the assistant
// remembers about your work, searchable. The search box IS the "ask your own memory" recall. Read
// view over the diary book's active entities (people / projects / decisions). Private — no share.
// DF7 / D17 (draft screen 12 "Control you can find later"): each remembered person carries a Forget
// action — an inline, worded confirm because the erasure is IRREVERSIBLE (KG entity + facts deleted,
// the name redacted from the diary prose). View + local confirm state only; the call lives in a hook.
import { useState } from 'react';
import { Search, User, Folder, Lock, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Sheet } from '@/components/shared/Sheet';
import type { GlossaryEntitySummary } from '@/features/glossary/types';
import type { ForgetResult } from '../../types';

export const MEMORY_SHEET_ID = 'memory';

const PERSON_KINDS = new Set(['colleague', 'person', 'org']);

export interface MobileMemorySheetProps {
  entities: GlossaryEntitySummary[];
  loading: boolean;
  error: string | null;
  search: string;
  onSearch: (q: string) => void;
  // D17 — forget a remembered person by name (null result = failed + toasted; leave it in the list).
  onForget?: (name: string) => Promise<ForgetResult | null>;
  forgettingName?: string | null;
  // FR / D17 — the "erase everything" danger-zone (the first-run's "erasable in one tap" promise,
  // honoured on the "Control you can find later" screen). Absent ⇒ the danger-zone is not rendered.
  onEraseAll?: () => Promise<boolean>;
  erasing?: boolean;
  // A4 (WS-2.10 / T18) — "I changed jobs": archive this epoch's facts + start fresh. Absent ⇒ not shown.
  onNewEpoch?: () => Promise<unknown>;
  newEpochStarting?: boolean;
}

export function MobileMemorySheet({
  entities,
  loading,
  error,
  search,
  onSearch,
  onForget,
  forgettingName,
  onEraseAll,
  erasing,
  onNewEpoch,
  newEpochStarting,
}: MobileMemorySheetProps) {
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [confirmErase, setConfirmErase] = useState(false);
  const [confirmEpoch, setConfirmEpoch] = useState(false);

  return (
    <Sheet id={MEMORY_SHEET_ID} title="What I know" description="Everything I remember about your work — private, never shared.">
      <div className="flex flex-col gap-3" data-testid="memory-sheet">
        {/* Recall — search your own memory */}
        <label className="flex items-center gap-2 rounded-lg border border-border bg-card px-3">
          <Search className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          <input
            type="search"
            value={search}
            onChange={(e) => onSearch(e.target.value)}
            placeholder="Ask your memory — a name, a project…"
            aria-label="Search your memory"
            data-testid="memory-search"
            className="min-h-[44px] flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
        </label>

        <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <Lock className="h-3 w-3" aria-hidden="true" /> Private · only you can see this
        </div>

        {loading && entities.length === 0 && (
          <p className="py-6 text-center text-sm text-muted-foreground">Loading your memory…</p>
        )}
        {error && <p className="py-4 text-center text-sm text-destructive">{error}</p>}
        {!loading && !error && entities.length === 0 && (
          <p className="py-8 text-center text-sm text-muted-foreground">
            {search ? 'Nothing remembered matches that yet.' : 'Nothing kept yet — end a day to build your memory.'}
          </p>
        )}

        <ul className="flex flex-col gap-2" data-testid="memory-list">
          {entities.map((e) => {
            const person = PERSON_KINDS.has(e.kind?.code ?? '');
            const Icon = person ? User : Folder;
            const confirming = confirmId === e.entity_id;
            const busy = forgettingName === e.display_name;
            return (
              <li key={e.entity_id} className="flex flex-col rounded-lg border border-border bg-card">
                <div className="flex items-start gap-3 p-3">
                  <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground">
                    <Icon className="h-4 w-4" aria-hidden="true" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium">{e.display_name}</div>
                    <div className="truncate text-xs text-muted-foreground">
                      {e.kind?.name ?? 'Noted'}
                      {e.short_description ? ` · ${e.short_description}` : ''}
                    </div>
                  </div>
                  {/* Forget is offered only for PEOPLE (the BFF's forget resolves a person by name). */}
                  {onForget && person && !confirming && (
                    <button
                      type="button"
                      data-testid={`memory-forget-${e.entity_id}`}
                      aria-label={`Forget ${e.display_name}`}
                      onClick={() => setConfirmId(e.entity_id)}
                      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:text-destructive"
                    >
                      <Trash2 className="h-4 w-4" aria-hidden="true" />
                    </button>
                  )}
                </div>

                {/* Irreversible — a worded confirm, not a bare icon (draft rev.3 tremor-safe pattern). */}
                {confirming && onForget && (
                  <div
                    className="flex flex-col gap-2 border-t border-border p-3"
                    data-testid={`memory-forget-confirm-${e.entity_id}`}
                  >
                    <p className="text-xs text-muted-foreground">
                      Forget <span className="font-medium text-foreground">{e.display_name}</span>? This erases
                      what I know about them and clears the name from your journal. It can&apos;t be undone.
                    </p>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        data-testid={`memory-forget-do-${e.entity_id}`}
                        disabled={busy}
                        onClick={async () => {
                          const res = await onForget(e.display_name);
                          if (res?.forgotten) setConfirmId(null); // parent refetches; failure keeps confirm open
                        }}
                        className={cn(
                          'flex min-h-[40px] flex-1 items-center justify-center rounded-md px-3 text-sm font-medium',
                          'bg-destructive text-destructive-foreground hover:bg-destructive/90 disabled:opacity-50',
                        )}
                      >
                        {busy ? 'Forgetting…' : 'Forget'}
                      </button>
                      <button
                        type="button"
                        data-testid={`memory-forget-keep-${e.entity_id}`}
                        disabled={busy}
                        onClick={() => setConfirmId(null)}
                        className="flex min-h-[40px] items-center justify-center rounded-md border border-border px-4 text-sm disabled:opacity-50"
                      >
                        Keep
                      </button>
                    </div>
                  </div>
                )}
              </li>
            );
          })}
        </ul>

        {/* A4 — "I changed jobs": archive this chapter's memories + start fresh. Not a delete (the old
            facts are set aside, not erased), but it changes what recall sees — so a worded confirm. */}
        {onNewEpoch && (
          <div className="mt-2 flex flex-col gap-2 rounded-lg border border-border p-3" data-testid="memory-new-epoch">
            {!confirmEpoch ? (
              <button
                type="button"
                data-testid="memory-new-epoch-open"
                onClick={() => setConfirmEpoch(true)}
                className="flex min-h-[44px] items-center justify-center gap-2 rounded-md text-sm font-medium text-foreground hover:bg-secondary"
              >
                Changed jobs? Start a new chapter
              </button>
            ) : (
              <div className="flex flex-col gap-2" data-testid="memory-new-epoch-confirm">
                <p className="text-xs text-muted-foreground">
                  Set aside everything I remember from your current chapter and start fresh? Past people &amp;
                  projects stop showing up in recall (they aren&apos;t deleted).
                </p>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    data-testid="memory-new-epoch-do"
                    disabled={newEpochStarting}
                    onClick={async () => {
                      const res = (await onNewEpoch()) as { epoch_closed?: boolean } | null;
                      if (res?.epoch_closed) setConfirmEpoch(false); // parent refetches; failure keeps it open
                    }}
                    className="flex min-h-[40px] flex-1 items-center justify-center rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                  >
                    {newEpochStarting ? 'Starting…' : 'Start a new chapter'}
                  </button>
                  <button
                    type="button"
                    data-testid="memory-new-epoch-cancel"
                    disabled={newEpochStarting}
                    onClick={() => setConfirmEpoch(false)}
                    className="flex min-h-[40px] items-center justify-center rounded-md border border-border px-4 text-sm disabled:opacity-50"
                  >
                    Keep
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Danger-zone — "erase everything" (the first-run promise). A worded confirm because it
            wipes ALL of your assistant data (memory + journal) and can't be undone. */}
        {onEraseAll && (
          <div className="mt-2 flex flex-col gap-2 rounded-lg border border-destructive/40 p-3" data-testid="memory-erase-all">
            {!confirmErase ? (
              <button
                type="button"
                data-testid="memory-erase-all-open"
                onClick={() => setConfirmErase(true)}
                className="flex min-h-[44px] items-center justify-center gap-2 rounded-md text-sm font-medium text-destructive hover:bg-destructive/10"
              >
                <Trash2 className="h-4 w-4" aria-hidden="true" />
                Erase everything
              </button>
            ) : (
              <div className="flex flex-col gap-2" data-testid="memory-erase-all-confirm">
                <p className="text-xs text-muted-foreground">
                  Erase <span className="font-medium text-foreground">everything</span> I remember and your whole
                  journal? This can&apos;t be undone.
                </p>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    data-testid="memory-erase-all-do"
                    disabled={erasing}
                    onClick={async () => {
                      const ok = await onEraseAll();
                      if (ok) setConfirmErase(false); // parent refetches; failure keeps confirm open
                    }}
                    className={cn(
                      'flex min-h-[40px] flex-1 items-center justify-center rounded-md px-3 text-sm font-medium',
                      'bg-destructive text-destructive-foreground hover:bg-destructive/90 disabled:opacity-50',
                    )}
                  >
                    {erasing ? 'Erasing…' : 'Erase everything'}
                  </button>
                  <button
                    type="button"
                    data-testid="memory-erase-all-cancel"
                    disabled={erasing}
                    onClick={() => setConfirmErase(false)}
                    className="flex min-h-[40px] items-center justify-center rounded-md border border-border px-4 text-sm disabled:opacity-50"
                  >
                    Keep
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </Sheet>
  );
}
