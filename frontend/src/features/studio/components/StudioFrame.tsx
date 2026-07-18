// The studio frame composition for ONE book. Mounted with key={bookId} by the page so an
// in-session book switch (/books/A/studio → /books/B/studio, same route, param change —
// React Router keeps the page mounted) cleanly re-derives ALL per-book state: useStudioChrome
// re-initialises, StudioDock re-seeds, and the StudioHost registry/bus re-create under the
// correct keys. Without the remount, book B would render book A's chrome/layout/registry (the
// review-impl HIGH #1/#2 root cause).
import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth';
import { booksApi } from '@/features/books/api';
import { useStudioChrome } from '../hooks/useStudioChrome';
import { StudioHostProvider, useStudioBusSelector, useStudioHost } from '../host/StudioHostProvider';
import { QuickOpen } from '../palette/QuickOpen';
import { CommandPalette } from '../palette/CommandPalette';
import { usePaletteHotkeys, type PaletteKind } from '../palette/usePaletteHotkeys';
import { revealManuscript } from '../palette/reveal';
import { OPENABLE_STUDIO_PANELS, getStudioPanelDef } from '../panels/catalog';
import { ManuscriptUnitProvider } from '../manuscript/unit/ManuscriptUnitProvider';
import type { JumpResult, ManuscriptNode } from '../manuscript/types';
import { useStudioOnboarding } from '../onboarding/useStudioOnboarding';
import { useStudioTour } from '../onboarding/useStudioTour';
import { STUDIO_TOURS, type StudioTourId } from '../onboarding/tours';
import { StudioOnboardingOverlay } from '../onboarding/StudioOnboardingOverlay';
import { StudioGuidedTour } from '../onboarding/StudioGuidedTour';
import { StudioTopBar } from './StudioTopBar';
import { StudioActivityBar } from './StudioActivityBar';
import { StudioSideBar } from './StudioSideBar';
import { StudioDock } from './StudioDock';
import { StudioBottomPanel } from './StudioBottomPanel';
import { StudioStatusBar } from './StudioStatusBar';
import { StudioStatusContributions } from '../statusbar/StudioStatusContributions';

export function StudioFrame({ bookId, initialChapterId }: { bookId: string; initialChapterId?: string }) {
  return (
    <StudioHostProvider bookId={bookId}>
      <StudioFrameInner bookId={bookId} initialChapterId={initialChapterId} />
    </StudioHostProvider>
  );
}

function StudioFrameInner({ bookId, initialChapterId }: { bookId: string; initialChapterId?: string }) {
  const { t } = useTranslation('studio');
  const { accessToken } = useAuth();
  const host = useStudioHost();
  const [bookTitle, setBookTitle] = useState('');
  const [bookLanguage, setBookLanguage] = useState<string | undefined>();

  const chrome = useStudioChrome(bookId);
  const [palette, setPalette] = useState<PaletteKind | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  // #19 — Studio onboarding (role picker overlay) + the guided tour (the account's role tour if
  // one's set, else `core` — #19 Wave 2). Both live here (not inside a dock panel) since
  // CommandPalette/WelcomePanel need to trigger them across a component-tree boundary dockview
  // panels can't otherwise cross (DOCK-4).
  const onboarding = useStudioOnboarding();
  const tour = useStudioTour((panelId) => host.openPanel(panelId));

  // #19 — WelcomePanel/UserGuidePanel (true dockview panels, isolated from this tree per DOCK-4)
  // ask to start a tour via the bus instead of a prop callback. `seenTourRequestSeq` starts at the
  // CURRENT value (not 0) so this never fires on mount — only on a genuinely NEW request published
  // after. A `tourId` (the tour-picker's per-topic buttons) starts that exact tour; an omitted
  // `tourId` (the WelcomePanel's quick-start button) falls back to the account's role tour.
  const guidedTourRequestSeq = useStudioBusSelector((s) => s.guidedTourRequestSeq ?? 0);
  const guidedTourRequestedId = useStudioBusSelector((s) => s.guidedTourRequestedId);
  const seenTourRequestSeq = useRef(guidedTourRequestSeq);
  useEffect(() => {
    if (guidedTourRequestSeq !== seenTourRequestSeq.current) {
      seenTourRequestSeq.current = guidedTourRequestSeq;
      const requested = guidedTourRequestedId as StudioTourId | undefined;
      const tourId = requested && requested in STUDIO_TOURS ? requested : (onboarding.role ?? 'core');
      tour.start(tourId);
    }
  }, [guidedTourRequestSeq, guidedTourRequestedId, tour, onboarding.role]);

  // #19 G10c — suppress the palette hotkey while a tour is active (an active tour is a
  // modal-like focused state and should win); the palette's own onSelect already closes it
  // immediately after dispatching "Studio: Start Guided Tour", so no other suppression is needed.
  usePaletteHotkeys((kind) => { if (!tour.active) setPalette(kind); });

  // #16 1.5 — a deep-linked chapter (ChaptersTab row-click/pencil, ?chapter=<id>) focuses the
  // manuscript unit + opens the editor dock exactly once, same seam as Quick Open/Navigator.
  useEffect(() => {
    if (initialChapterId) host.focusManuscriptUnit(initialChapterId);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per mount only, not on every
    // host/initialChapterId identity change (StudioFrame is remounted per-book via key={bookId}).
  }, []);

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
  // #12 M-C: a SCENE hit additionally publishes the scene slice (AFTER the chapter focus — the
  // chapter reducer clears activeSceneId) so the editor's Scene Rail highlights it.
  const resolveJump = useCallback((r: JumpResult) => {
    revealManuscript(chrome);
    setSelectedNodeId(r.id);
    if (r.chapterId) {
      host.focusManuscriptUnit(r.chapterId);
      if (r.kind === 'scene') host.publish({ type: 'scene', sceneId: r.id, chapterId: r.chapterId });
    }
  }, [chrome, host]);

  // Navigator select (Debt #1 navigator→dock): highlight + drive the editor via the one seam
  // (publish chapter → the Tier-4 hoist loads it; open the editor dock). Arc rows have no chapterId.
  const onSelectNode = useCallback((node: ManuscriptNode) => {
    setSelectedNodeId(node.id);
    if (node.chapterId) {
      host.focusManuscriptUnit(node.chapterId);
      if (node.kind === 'scene') host.publish({ type: 'scene', sceneId: node.id, chapterId: node.chapterId });
    }
  }, [host]);

  return (
    <div className="flex h-screen w-full flex-col overflow-hidden bg-background">
      <StudioTopBar bookId={bookId} bookTitle={bookTitle} onOpenQuickOpen={() => setPalette('quick')} />

      {/* Tier-4 manuscript unit hoisted ABOVE dockview (#08) so the editor's in-flight edits
          survive a dock float / close, and the Lane-B reconciler + editor read one owner store.
          #12 M-H moved it above the STATUS BAR too (the word-count item reads the hoist) — it
          sits above every chrome conditional, so a sidebar/bottom toggle never remounts it. */}
      <ManuscriptUnitProvider bookId={bookId}>
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
              width={chrome.sidebarWidth}
              onResize={chrome.setSidebarWidth}
            />
          )}

          <div className="flex min-w-0 flex-1 flex-col">
            {/* The dock stays mounted regardless of the bottom panel / sidebar (D4 no-remount:
                in-flight panels must never be dropped by a chrome toggle). */}
            <StudioDock bookId={bookId} apiRef={host._dockApiRef} />
            {chrome.bottomOpen && <StudioBottomPanel onClose={chrome.toggleBottom} />}
          </div>
        </div>

        {/* #11 F2 — ambient status items (badge/meter) live at frame level, not in panels. */}
        <StudioStatusContributions />
        <StudioStatusBar
          bookLanguage={bookLanguage}
          bottomOpen={chrome.bottomOpen}
          onToggleBottom={chrome.toggleBottom}
        />
      </ManuscriptUnitProvider>

      {/* Palettes (always mounted so the shared jump layer persists; visibility via `open`). */}
      <QuickOpen open={palette === 'quick'} onClose={() => setPalette(null)} bookId={bookId} token={accessToken} onResolve={resolveJump} />
      <CommandPalette
        open={palette === 'command'}
        onClose={() => setPalette(null)}
        chrome={chrome}
        panels={OPENABLE_STUDIO_PANELS}
        onOpenQuickOpen={() => setPalette('quick')}
        onOpenPanel={openStudioPanel}
        onChooseYourFocus={onboarding.reopen}
        onStartGuidedTour={() => tour.start(onboarding.role ?? 'core')}
      />

      {/* #19 — the role-picker overlay + guided tour, above the mounted dock (not dock panels
          themselves — DOCK-1..11 govern panels/**, not this frame-level chrome). */}
      <StudioOnboardingOverlay
        open={onboarding.shouldShow}
        onChooseRole={onboarding.chooseRole}
        onSkip={onboarding.skip}
      />
      <StudioGuidedTour tour={tour} />
    </div>
  );
}
