// FD-16/FD-15 — shared glossary-entity roster.
// The canon entity_id picker (FD-16) and the planner cast picker (FD-15) both
// need the project book's glossary entities as {id,label} options. Reuses the
// glossary feature's `listEntities` (read-only, react-query-cached) rather than
// re-implementing the call. Returns lightweight options for a <select>.
import { useQuery } from '@tanstack/react-query';
import { glossaryApi } from '../../glossary/api';
import { defaultFilters } from '../../glossary/types';

export type RosterOption = { id: string; label: string };

// One bounded page (books are user-curated — hundreds of entities at most). The
// picker is a flat select; if a book ever exceeds this, the picker would need
// server-side search (the WikiTab entity-picker pattern) — out of scope here.
const ROSTER_LIMIT = 500;

export function useGlossaryRoster(bookId: string | undefined, token: string | null) {
  return useQuery({
    queryKey: ['composition', 'glossary-roster', bookId],
    queryFn: () =>
      glossaryApi.listEntities(
        bookId!,
        { ...defaultFilters, limit: ROSTER_LIMIT, offset: 0 },
        token!,
      ),
    enabled: !!bookId && !!token,
    select: (d): RosterOption[] =>
      d.items.map((e) => ({ id: e.entity_id, label: e.display_name })),
  });
}
