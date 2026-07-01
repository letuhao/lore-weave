// Writing Studio (v2) — the frame composition.
//
// A NEW, from-scratch surface (does NOT touch ChapterEditorPage). This page is a thin
// composition of the fixed chrome regions around the dockview centre; each region is its own
// component under features/studio. Panels (real tools) are added one at a time later.
//
// Spec: docs/specs/2026-07-01-writing-studio/ (00_OVERVIEW.md + 01_skeleton.md).
import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useAuth } from '@/auth';
import { booksApi } from '@/features/books/api';
import { useStudioChrome } from '@/features/studio/hooks/useStudioChrome';
import { StudioTopBar } from '@/features/studio/components/StudioTopBar';
import { StudioActivityBar } from '@/features/studio/components/StudioActivityBar';
import { StudioSideBar } from '@/features/studio/components/StudioSideBar';
import { StudioDock } from '@/features/studio/components/StudioDock';
import { StudioBottomPanel } from '@/features/studio/components/StudioBottomPanel';
import { StudioStatusBar } from '@/features/studio/components/StudioStatusBar';

export function WritingStudioPage() {
  const { bookId = '' } = useParams();
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
          {/* The dock stays mounted regardless of the bottom panel (no remount of in-flight
              panels when the bottom toggles). */}
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
