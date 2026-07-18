import { useTranslation } from 'react-i18next';
import { BookOpen, Search } from 'lucide-react';
import { useLoreSeeker } from '../hooks/useLoreSeeker';

// W11 lore-seeker — the reader-side "ask the lore" panel. It shows an entity's known facts
// SPOILER-WINDOWED to the chapter the reader is on: the server fetches facts with
// before_chapter_id = the current chapter and fails CLOSED, so a reader only ever sees what the
// story has revealed by where they've read. A reader with no position sees nothing. View-only.
export function LoreSeekerPanel({ bookId, chapterId }: { bookId: string; chapterId: string }) {
  const { t } = useTranslation('books');
  const s = useLoreSeeker(bookId, chapterId);

  return (
    <div className="flex h-full flex-col gap-3 p-3" data-testid="lore-seeker">
      <div className="flex items-center gap-2 text-sm font-medium">
        <BookOpen className="h-4 w-4" />
        {t('lore.heading', { defaultValue: 'Lore so far' })}
      </div>
      <p className="text-xs text-muted-foreground">
        {t('lore.subtitle', {
          defaultValue: 'What the story has revealed up to where you are reading — no spoilers from later chapters.',
        })}
      </p>

      {/* Search the book's people, places and things. */}
      <div className="relative">
        <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
        <input
          value={s.query}
          onChange={(e) => s.setQuery(e.target.value)}
          placeholder={t('lore.search', { defaultValue: 'Search the story…' })}
          data-testid="lore-search"
          className="w-full rounded-md border bg-background py-1.5 pl-7 pr-2 text-sm"
        />
      </div>

      {/* Entity results. */}
      <ul className="space-y-1 overflow-y-auto" data-testid="lore-entities">
        {s.entities.map((e) => (
          <li key={e.id}>
            <button
              onClick={() => s.select(e.id)}
              data-testid={`lore-entity-${e.id}`}
              className={`w-full rounded px-2 py-1 text-left text-sm ${
                e.id === s.selectedId ? 'bg-muted font-semibold' : 'hover:bg-muted/60'
              }`}
            >
              {e.name}
              {e.kind && <span className="ml-1 text-xs text-muted-foreground">· {e.kind}</span>}
            </button>
          </li>
        ))}
      </ul>

      {/* The windowed facts — the spoiler gate lives here. */}
      {s.selectedId && (
        <div className="border-t pt-2" data-testid="lore-facts">
          {!s.hasPosition ? (
            <p className="text-xs text-muted-foreground" data-testid="lore-no-position">
              {t('lore.noPosition', {
                defaultValue: 'Open a chapter to see what has been revealed by that point.',
              })}
            </p>
          ) : s.isFactsLoading ? null : s.facts.length === 0 ? (
            <p className="text-xs text-muted-foreground" data-testid="lore-nothing-yet">
              {t('lore.nothingYet', {
                defaultValue: 'Nothing has been revealed about this yet — keep reading.',
              })}
            </p>
          ) : (
            <ul className="space-y-1">
              {s.facts.map((f) => (
                <li key={f.id} className="text-xs" data-testid={`lore-fact-${f.id}`}>
                  <span className="rounded bg-muted px-1 text-[10px] uppercase text-muted-foreground">{f.type}</span>{' '}
                  {f.content}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
