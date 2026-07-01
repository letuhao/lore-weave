// The studio frame composition for ONE book. Mounted with key={bookId} by the page so an
// in-session book switch (/books/A/studio → /books/B/studio, same route, param change —
// React Router keeps the page mounted) cleanly re-derives ALL per-book state: useStudioChrome
// re-initialises, StudioDock re-seeds, and the StudioHost registry/bus re-create under the
// correct keys. Without the remount, book B would render book A's chrome/layout/registry (the
// review-impl HIGH #1/#2 root cause).
import { useCallback, useEffect, useRef, useState } from 'react';
import type { DockviewApi } from 'dockview-react';
import { useAuth } from '@/auth';
import { booksApi } from '@/features/books/api';
import { useStudioChrome } from '../hooks/useStudioChrome';
import { StudioHostProvider, useStudioHost } from '../host/StudioHostProvider';
import { QuickOpen } from '../palette/QuickOpen';
import { CommandPalette } from '../palette/CommandPalette';
import { usePaletteHotkeys, type PaletteKind } from '../palette/usePaletteHotkeys';
import { revealManuscript } from '../palette/reveal';
import type { JumpResult } from '../manuscript/types';
import { StudioTopBar } from './StudioTopBar';
import { StudioActivityBar } from './StudioActivityBar';
import { StudioSideBar } from './StudioSideBar';
import { StudioDock } from './StudioDock';
import { StudioBottomPanel } from './StudioBottomPanel';
import { StudioStatusBar } from './StudioStatusBar';

export function StudioFrame({ bookId }: { bookId: string }) {
  return (
    <StudioHostProvider bookId={bookId}>
      <StudioFrameInner bookId={bookId} />
    </StudioHostProvider>
  );
}

function StudioFrameInner({ bookId }: { bookId: string }) {
  const { accessToken } = useAuth();
  const host = useStudioHost();
  const [bookTitle, setBookTitle] = useState('');
  const [bookLanguage, setBookLanguage] = useState<string | undefined>();

  const chrome = useStudioChrome(bookId);
  const [palette, setPalette] = useState<PaletteKind | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const dockApiRef = useRef<DockviewApi | null>(null);

  usePaletteHotkeys(setPalette);

  useEffect(() => {
    if (!accessToken || !bookId) return;
    let mounted = true;
    booksApi.getBook(accessToken, bookId)
      .then((b) => { if (mounted) { setBookTitle(b.title || ''); setBookLanguage(b.original_language ?? undefined); } })
      .catch(() => { /* title/lang are cosmetic */ });
    return () => { mounted = false; };
  }, [accessToken, bookId]);

  // Command Palette "Studio: Open <panel>" → focus if already docked, else add. The component id
  // must be a registered dockview component (a built panel); until #03 lands the registry is
  // empty so this is dormant — guarded so an unknown id degrades to a no-op, never a crash.
  const openPanel = useCallback((panelId: string) => {
    const api = dockApiRef.current;
    if (!api) return;
    const existing = api.getPanel(panelId);
    if (existing) { existing.api.setActive(); return; }
    const tool = host.getTool(panelId);
    try { api.addPanel({ id: panelId, component: panelId, title: tool?.label ?? panelId }); }
    catch { /* component not registered (panel not built yet) — no-op */ }
  }, [host]);

  // Quick Open resolve (v1): reveal the Manuscript navigator (without toggling it shut if we're
  // already there — review-impl MED), highlight the hit, publish to the bus. Tree reveal (expand
  // ancestors + scroll) and dock-open land with #03 (tracked debt).
  const resolveJump = useCallback((r: JumpResult) => {
    revealManuscript(chrome);
    setSelectedNodeId(r.id);
    if (r.chapterId) host.publish({ type: 'chapter', chapterId: r.chapterId, bookId });
  }, [chrome, host, bookId]);

  return (
    <div className="flex h-screen w-full flex-col overflow-hidden bg-background">
      <StudioTopBar bookId={bookId} bookTitle={bookTitle} onOpenQuickOpen={() => setPalette('quick')} />

      <div className="flex min-h-0 flex-1">
        <StudioActivityBar
          bookId={bookId}
          activeView={chrome.activeView}
          sidebarCollapsed={chrome.sidebarCollapsed}
          onSelect={chrome.setActiveView}
        />
        {!chrome.sidebarCollapsed && (
          <StudioSideBar
            activeView={chrome.activeView}
            onCollapse={chrome.toggleSidebar}
            bookId={bookId}
            token={accessToken}
            selectedId={selectedNodeId}
            onSelectNode={setSelectedNodeId}
          />
        )}

        <div className="flex min-w-0 flex-1 flex-col">
          {/* The dock stays mounted regardless of the bottom panel / sidebar (D4 no-remount:
              in-flight panels must never be dropped by a chrome toggle). */}
          <StudioDock bookId={bookId} apiRef={dockApiRef} />
          {chrome.bottomOpen && <StudioBottomPanel onClose={chrome.toggleBottom} />}
        </div>
      </div>

      <StudioStatusBar
        bookLanguage={bookLanguage}
        bottomOpen={chrome.bottomOpen}
        onToggleBottom={chrome.toggleBottom}
      />

      {/* Palettes (always mounted so the shared jump layer persists; visibility via `open`). */}
      <QuickOpen open={palette === 'quick'} onClose={() => setPalette(null)} bookId={bookId} token={accessToken} onResolve={resolveJump} />
      <CommandPalette
        open={palette === 'command'}
        onClose={() => setPalette(null)}
        chrome={chrome}
        onOpenQuickOpen={() => setPalette('quick')}
        onOpenPanel={openPanel}
      />
    </div>
  );
}
