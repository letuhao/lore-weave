// The studio frame composition for ONE book. Mounted with key={bookId} by the page so an
// in-session book switch (/books/A/studio → /books/B/studio, same route, param change —
// React Router keeps the page mounted) cleanly re-derives ALL per-book state: useStudioChrome
// re-initialises, StudioDock re-seeds, and the StudioHost registry/bus re-create under the
// correct keys. Without the remount, book B would render book A's chrome/layout/registry (the
// review-impl HIGH #1/#2 root cause).
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth';
import { booksApi } from '@/features/books/api';
import { useStudioChrome } from '../hooks/useStudioChrome';
import { StudioHostProvider, useStudioHost } from '../host/StudioHostProvider';
import { QuickOpen } from '../palette/QuickOpen';
import { CommandPalette } from '../palette/CommandPalette';
import { usePaletteHotkeys, type PaletteKind } from '../palette/usePaletteHotkeys';
import { revealManuscript } from '../palette/reveal';
import { OPENABLE_STUDIO_PANELS, getStudioPanelDef } from '../panels/catalog';
import { ManuscriptUnitProvider } from '../manuscript/unit/ManuscriptUnitProvider';
import type { JumpResult, ManuscriptNode } from '../manuscript/types';
import { StudioTopBar } from './StudioTopBar';
import { StudioActivityBar } from './StudioActivityBar';
import { StudioSideBar } from './StudioSideBar';
import { StudioDock } from './StudioDock';
import { StudioBottomPanel } from './StudioBottomPanel';
import { StudioStatusBar } from './StudioStatusBar';
import { StudioStatusContributions } from '../statusbar/StudioStatusContributions';

export function StudioFrame({ bookId }: { bookId: string }) {
  return (
    <StudioHostProvider bookId={bookId}>
      <StudioFrameInner bookId={bookId} />
    </StudioHostProvider>
  );
}

function StudioFrameInner({ bookId }: { bookId: string }) {
  const { t } = useTranslation('studio');
  const { accessToken } = useAuth();
  const host = useStudioHost();
  const [bookTitle, setBookTitle] = useState('');
  const [bookLanguage, setBookLanguage] = useState<string | undefined>();

  const chrome = useStudioChrome(bookId);
  const [palette, setPalette] = useState<PaletteKind | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  usePaletteHotkeys(setPalette);

  useEffect(() => {
    if (!accessToken || !bookId) return;
    let mounted = true;
    booksApi.getBook(accessToken, bookId)
      .then((b) => { if (mounted) { setBookTitle(b.title || ''); setBookLanguage(b.original_language ?? undefined); } })
      .catch(() => { /* title/lang are cosmetic */ });
    return () => { mounted = false; };
  }, [accessToken, bookId]);

  // Command Palette "Studio: Open <panel>" → host.openPanel with the catalog title (a CLOSED
  // panel isn't registered yet, so the title comes from the catalog, not a live registration).
  const openStudioPanel = useCallback((panelId: string) => {
    const def = getStudioPanelDef(panelId);
    host.openPanel(panelId, { title: def ? t(def.titleKey, { defaultValue: panelId }) : undefined });
  }, [host, t]);

  // Quick Open resolve (v1): reveal the Manuscript navigator (without toggling it shut if we're
  // already there — review-impl MED), highlight the hit, publish the active chapter to the bus via
  // the host. Tree reveal (expand ancestors + scroll) and dock-open land with #03 (tracked debt).
  const resolveJump = useCallback((r: JumpResult) => {
    revealManuscript(chrome);
    setSelectedNodeId(r.id);
    if (r.chapterId) host.focusManuscriptUnit(r.chapterId);
  }, [chrome, host]);

  // Navigator select (Debt #1 navigator→dock): highlight + drive the editor via the one seam
  // (publish chapter → the Tier-4 hoist loads it; open the editor dock). Arc rows have no chapterId.
  const onSelectNode = useCallback((node: ManuscriptNode) => {
    setSelectedNodeId(node.id);
    if (node.chapterId) host.focusManuscriptUnit(node.chapterId);
  }, [host]);

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
            onSelectNode={onSelectNode}
          />
        )}

        {/* Tier-4 manuscript unit hoisted ABOVE dockview (#08) so the editor's in-flight edits
            survive a dock float / close, and the Lane-B reconciler + editor read one owner store. */}
        <ManuscriptUnitProvider bookId={bookId}>
          <div className="flex min-w-0 flex-1 flex-col">
            {/* The dock stays mounted regardless of the bottom panel / sidebar (D4 no-remount:
                in-flight panels must never be dropped by a chrome toggle). */}
            <StudioDock bookId={bookId} apiRef={host._dockApiRef} />
            {chrome.bottomOpen && <StudioBottomPanel onClose={chrome.toggleBottom} />}
          </div>
        </ManuscriptUnitProvider>
      </div>

      {/* #11 F2 — ambient status items (badge/meter) live at frame level, not in panels. */}
      <StudioStatusContributions />
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
        panels={OPENABLE_STUDIO_PANELS}
        onOpenQuickOpen={() => setPalette('quick')}
        onOpenPanel={openStudioPanel}
      />
    </div>
  );
}
