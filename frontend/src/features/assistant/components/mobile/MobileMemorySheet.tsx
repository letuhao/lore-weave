// DF6 view — "What I know" (draft screen 11) + Recall (draft screen 5): everything the assistant
// remembers about your work, searchable. The search box IS the "ask your own memory" recall. Read
// view over the diary book's active entities (people / projects / decisions). Private — no share.
import { Search, User, Folder, Lock } from 'lucide-react';
import { Sheet } from '@/components/shared/Sheet';
import type { GlossaryEntitySummary } from '@/features/glossary/types';

export const MEMORY_SHEET_ID = 'memory';

const PERSON_KINDS = new Set(['colleague', 'person', 'org']);

export interface MobileMemorySheetProps {
  entities: GlossaryEntitySummary[];
  loading: boolean;
  error: string | null;
  search: string;
  onSearch: (q: string) => void;
}

export function MobileMemorySheet({ entities, loading, error, search, onSearch }: MobileMemorySheetProps) {
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
            return (
              <li key={e.entity_id} className="flex items-start gap-3 rounded-lg border border-border bg-card p-3">
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
              </li>
            );
          })}
        </ul>
      </div>
    </Sheet>
  );
}
