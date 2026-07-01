// The studio frame composition for ONE book. Mounted with key={bookId} by the page so an
// in-session book switch (/books/A/studio → /books/B/studio, same route, param change —
// React Router keeps the page mounted) cleanly re-derives ALL per-book state: useStudioChrome
// re-initialises and StudioDock re-seeds under the correct localStorage keys. Without the
// remount, book B would render book A's chrome/layout and overwrite B's stored state (the
// review-impl HIGH #1/#2 root cause).
import { useEffect, useState } from 'react';
import { useAuth } from '@/auth';
import { booksApi } from '@/features/books/api';
import { useStudioChrome } from '../hooks/useStudioChrome';
import { StudioTopBar } from './StudioTopBar';
import { StudioActivityBar } from './StudioActivityBar';
import { StudioSideBar } from './StudioSideBar';
import { StudioDock } from './StudioDock';
import { StudioBottomPanel } from './StudioBottomPanel';
import { StudioStatusBar } from './StudioStatusBar';

export function StudioFrame({ bookId }: { bookId: string }) {
  const { accessToken } = useAuth();
  const [bookTitle, setBookTitle] = useState('');
  const [bookLanguage, setBookLanguage] = useState<string | undefined>();

  const chrome = useStudioChrome(bookId);

  useEffect(() => {
    if (!accessToken || !bookId) return;
    let mounted = true;
    booksApi.getBook(accessToken, bookId)
      .then((b) => { if (mounted) { setBookTitle(b.title || ''); setBookLanguage(b.original_language ?? undefined); } })
      .catch(() => { /* title/lang are cosmetic */ });
    return () => { mounted = false; };
  }, [accessToken, bookId]);

  return (
    <div className="flex h-full w-full flex-col overflow-hidden bg-background">
      <StudioTopBar bookId={bookId} bookTitle={bookTitle} />

      <div className="flex min-h-0 flex-1">
        <StudioActivityBar
          bookId={bookId}
          activeView={chrome.activeView}
          sidebarCollapsed={chrome.sidebarCollapsed}
          onSelect={chrome.setActiveView}
        />
        {!chrome.sidebarCollapsed && (
          <StudioSideBar activeView={chrome.activeView} onCollapse={chrome.toggleSidebar} />
        )}

        <div className="flex min-w-0 flex-1 flex-col">
          {/* The dock stays mounted regardless of the bottom panel / sidebar (D4 no-remount:
              in-flight panels must never be dropped by a chrome toggle). */}
          <StudioDock bookId={bookId} />
          {chrome.bottomOpen && <StudioBottomPanel onClose={chrome.toggleBottom} />}
        </div>
      </div>

      <StudioStatusBar
        bookLanguage={bookLanguage}
        bottomOpen={chrome.bottomOpen}
        onToggleBottom={chrome.toggleBottom}
      />
    </div>
  );
}
