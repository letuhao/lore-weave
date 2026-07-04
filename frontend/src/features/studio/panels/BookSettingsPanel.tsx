// 17_translation_enrichment_sharing_settings_docks.md — the `book-settings` dock panel: basic
// info edit, cover upload/preview/remove, genre tags multi-select + genre-impact preview, world
// cross-link, dirty-tracking save bar. Thin wrapper (DOCK-2) reusing the classic SettingsTab
// AS-IS — review-impl fix: the first version of this panel forked SettingsTab's ~400 lines of
// logic wholesale instead of reusing it, exactly the DOCK-2/SDK-First violation the standard
// exists to prevent (two independent copies of the same form/save/cover/genre logic that would
// silently drift). SettingsTab already took `bookId`/`book`/`onReload` as props (route-agnostic);
// it now also takes an optional `onOpenWorld` so this panel can inject a studio-safe handler
// instead of SettingsTab's own default route-navigation — mirrors BookWorldSection's own
// onOpenWorld shape.
//
// Note: `id="book-settings"` deliberately — NOT `settings` (that id is the existing user-level
// account/providers/translation panel; colliding the two would break DOCK-6's enum-lockstep
// contract, per the spec).
import { useQuery } from '@tanstack/react-query';
import type { IDockviewPanelProps } from 'dockview-react';
import { useAuth } from '@/auth';
import { booksApi } from '@/features/books/api';
import { SettingsTab } from '@/pages/book-tabs/SettingsTab';
import { Skeleton } from '@/components/shared';
import { useStudioHost } from '../host/StudioHostProvider';
import { followStudioLink } from '../host/studioLinks';
import { useStudioPanel } from './useStudioPanel';

export function BookSettingsPanel(props: IDockviewPanelProps) {
  useStudioPanel('book-settings', props.api);
  const host = useStudioHost();
  const { bookId } = host;
  const { accessToken } = useAuth();

  const { data: book, refetch } = useQuery({
    queryKey: ['book', bookId],
    queryFn: () => booksApi.getBook(accessToken!, bookId),
    enabled: !!accessToken,
  });

  if (!book) {
    return (
      <div data-testid="studio-book-settings-loading" className="space-y-3 p-6">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  return (
    <div data-testid="studio-book-settings-panel" className="h-full min-h-0 overflow-auto">
      <SettingsTab
        bookId={bookId}
        book={book}
        onReload={() => void refetch()}
        onOpenWorld={(worldId) => followStudioLink(`/worlds/${worldId}`, host, { bookId: host.bookId })}
      />
    </div>
  );
}
