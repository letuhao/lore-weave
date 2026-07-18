// Side bar (resizable slot, collapsible) — hosts the active navigator. Manuscript is a real
// navigator (#02); the other views are still per-view stubs (built as later components).
import { useTranslation } from 'react-i18next';
import { PanelLeftClose } from 'lucide-react';
import type { ActivityView } from '../types';
import { ManuscriptNavigator } from '../manuscript/ManuscriptNavigator';
import { useChapterDoor } from '../manuscript/useChapterDoor';
import type { ManuscriptNode } from '../manuscript/types';
import { useStudioHost } from '../host/StudioHostProvider';
import { useSidebarResize } from '../hooks/useSidebarResize';
import { PlanNavigatorRail } from '@/features/plan-hub/components';
import { BIBLE_NAV_PANELS } from '../panels/catalog';
import { SearchNavigatorRail } from '../search/SearchNavigatorRail';

interface Props {
  activeView: ActivityView;
  onCollapse: () => void;
  bookId: string;
  token: string | null;
  // Selection is HOISTED to the frame so Quick Open (#06a) can drive the highlight too. The full
  // node is passed (the frame needs chapterId to open the editor — Debt #1 navigator→dock).
  selectedId: string | null;
  onSelectNode: (node: ManuscriptNode) => void;
  // Width + resize live in the frame's chrome state (per-book, per-device localStorage) so the
  // sidebar is resizable like a real dock panel. `onResize(width, persist)` updates live during a
  // drag and persists only on release.
  width: number;
  onResize: (width: number, persist: boolean) => void;
}

export function StudioSideBar({ activeView, onCollapse, bookId, token, selectedId, onSelectNode, width, onResize }: Props) {
  const { t } = useTranslation('studio');
  const host = useStudioHost();
  const { resizing, handleProps } = useSidebarResize({ width, onResize });
  // M3 (F2) — the rail's own "＋ Chapter" create-and-open door (the sealed amendment). Shares the one
  // useChapterDoor with the Editor empty state + Plan Hub, so all three doors behave identically.
  const chapterDoor = useChapterDoor(bookId);

  return (
    <div
      data-testid="studio-sidebar"
      style={{ width }}
      className="relative flex flex-shrink-0 flex-col border-r bg-card"
    >
      {activeView === 'manuscript' ? (
        // The navigator owns its full view header (title + New/Collapse-all/Reload + collapse),
        // so the Side Bar renders NO chrome header here — a single header, VS Code-style.
        //
        // `onNewChapter` is REQUIRED, not optional-in-practice: the navigator renders its `+` as
        // `disabled={!onNewChapter}`, and this is its ONLY consumer. Dropping it (as this file did
        // until 2026-07-17) disabled the button 100% of the time, for every user, on every book —
        // and with the Editor's empty state pointing back at the navigator, that closed the Studio's
        // zero-state loop: nothing in it could create the first thing.
        // (docs/bugs/2026-07-17-studio-first-use-cold-start.md)
        //
        // It OPENS THE PLAN, it does not create a chapter. Structure authoring is a SPEC act, and the
        // rail contract below is explicit — Manuscript = prose, Plan = spec — so the `+` hands off to
        // the surface that owns structure rather than growing a rival authoring path here. plan-hub's
        // empty state carries the actual origin verb ("Start with your first arc"), which is what
        // makes this a real exit and not just a relocated dead end.
        <ManuscriptNavigator
          bookId={bookId}
          token={token}
          selectedId={selectedId}
          onSelect={(node) => onSelectNode(node)}
          onNewChapter={() => host.openPanel('plan-hub', { focus: true })}
          onCreateChapter={chapterDoor.startNewChapter ?? undefined}
          creatingChapter={chapterDoor.creating}
          onCollapseSidebar={onCollapse}
        />
      ) : activeView === 'plan' ? (
        // 24 PH25 — the Plan navigator is an ACTIVITY BAR rail, not a dock panel: it and the Hub
        // canvas are two densities of ONE dataset. Its click contract is fixed and is the whole
        // reason the two rails aren't ambiguous:
        //     Manuscript row → the EDITOR (the prose)
        //     Plan row       → the HUB CANVAS (the spec), opening plan-hub if it's closed
        // It sits outside the dock, so it cannot hand the Hub a callback — it asks over the bus
        // (the same seam the guided-tour request and ui_focus_manuscript_unit already use).
        <PlanNavigatorRail
          bookId={bookId}
          selectedId={selectedId}
          onFocusNode={(nodeId) => {
            host.openPanel('plan-hub', { focus: true });
            host.publish({ type: 'planFocusNode', nodeId });
          }}
        />
      ) : (
        <>
          <div className="flex h-[34px] flex-shrink-0 items-center justify-between border-b px-3">
            <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
              {t(`activity.${activeView}`, { defaultValue: activeView })}
            </span>
            <button
              type="button"
              onClick={onCollapse}
              title={t('sidebar.collapse', { defaultValue: 'Collapse' })}
              className="flex h-5 w-5 items-center justify-center rounded text-muted-foreground hover:bg-secondary hover:text-foreground"
            >
              <PanelLeftClose className="h-3.5 w-3.5" />
            </button>
          </div>

          {/* H-1b — the `bible` view is a real rail: a launcher list of the bible-group panels.
              S-11 — `search` is now a real query rail too (was a stub). quality keeps its single
              hub button (DOCK-8). */}
          {activeView === 'search' ? (
            <SearchNavigatorRail />
          ) : activeView === 'bible' ? (
            <div data-testid="studio-sidebar-bible" className="flex flex-1 flex-col gap-0.5 overflow-y-auto p-2">
              {BIBLE_NAV_PANELS.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  data-testid={`studio-sidebar-open-${p.id}`}
                  onClick={() => host.openPanel(p.id)}
                  className="rounded px-2 py-1.5 text-left text-[12px] text-foreground/80 hover:bg-secondary hover:text-foreground"
                >
                  {t(p.titleKey, { defaultValue: p.id })}
                </button>
              ))}
            </div>
          ) : (
            <div className="flex flex-1 flex-col items-center justify-center gap-1.5 p-6 text-center">
              <p className="text-xs font-medium text-foreground/70">
                {t(`navStub.${activeView}.title`, { defaultValue: activeView })}
              </p>
              <p className="max-w-[200px] text-[11px] leading-relaxed text-muted-foreground">
                {t(`navStub.${activeView}.body`, { defaultValue: 'Built next.' })}
              </p>
              {activeView === 'quality' && (
                <button
                  type="button"
                  data-testid="studio-sidebar-open-quality"
                  onClick={() => host.openPanel('quality')}
                  className="mt-2 rounded bg-primary px-3 py-1 text-[11px] text-primary-foreground hover:opacity-90"
                >
                  {t('panels.quality.title', { defaultValue: 'Quality' })}
                </button>
              )}
            </div>
          )}
        </>
      )}

      {/* Resize handle — a thin strip on the right edge. Pointer-drag (with capture) resizes the
          sidebar like a dock sash; double-click resets to default. The invisible strip is wider
          than the visible line so it's easy to grab; the line brightens on hover / during drag. */}
      <div
        {...handleProps}
        data-testid="studio-sidebar-resize"
        role="separator"
        aria-orientation="vertical"
        aria-label={t('sidebar.resize', { defaultValue: 'Resize side bar' })}
        title={t('sidebar.resize', { defaultValue: 'Resize side bar' })}
        className="group absolute inset-y-0 right-0 z-20 w-1.5 translate-x-1/2 cursor-col-resize touch-none"
      >
        <div
          className={`mx-auto h-full w-px transition-colors ${resizing ? 'bg-primary' : 'bg-transparent group-hover:bg-primary/60'}`}
        />
      </div>

      {/* While dragging, a full-window overlay keeps the pointer/cursor ours even over dock iframes
          (pointer capture already routes events here; the overlay just fixes the cursor + blocks
          accidental hovers). Rendered only during a live drag. */}
      {resizing && <div className="fixed inset-0 z-50 cursor-col-resize" data-testid="studio-sidebar-resize-overlay" />}
    </div>
  );
}
