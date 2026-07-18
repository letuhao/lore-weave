// 24 Plan Hub v2 (H2.1 + H3 + H2.6 bus/camera) — the `plan-hub` dock panel: the whole package on the
// graph canvas. TOOLBAR (PH15) · graph CANVAS (React Flow, positions from the pure laneLayout —
// PH14) · right DETAIL DRAWER (H3, over the canvas) · the PH21 unplanned tray docked beneath.
//
// The Plan NAVIGATOR is deliberately NOT in here. PH25 puts it in the ACTIVITY BAR (it and the canvas
// are two densities of one dataset), and OQ-6 ✅ rejects a third in-panel list as a duplicate of it.
// It reaches us over the studio bus (`planFocusNode`) — it lives outside the dock and cannot hand us
// a callback.
//
// Logic lives in usePlanHub (the controller producing PlanHubView); this file wires it to the
// regions, subscribes the bus, and self-registers as a studio panel. Book-scoped.
//
// Selection is ONE piece of state (view.selectedId) shared across all three: a canvas node click, a
// rail row click (onFocusNode), and the drawer all read/write it. A rail/canvas selection whose kind
// is arc/saga resolves against the SAME shell the rail draws (rollup node id === structure_node id,
// laneLayout); a chapter/scene resolves via the drawer's per-node fetch.
//
// H2.6 bus: subscribe the editor's active-chapter signal (focusManuscriptUnit publishes it — verified
// in StudioHostProvider) → a "you are here" highlight on the node whose chapterId matches. OQ-5 camera:
// a rail focus pans the canvas to the node (focusNode = select + bump the focus seq). The reverse
// publish (planHub.selection) is deferred — no consumer reads a Hub-selection bus slice yet.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { IDockviewPanelProps } from 'dockview-react';
import { useStudioBusSelector, useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { booksApi } from '@/features/books/api';
import { useWorkResolution } from '@/features/composition/hooks/useWork';
import { usePlanHub } from '@/features/plan-hub/hooks/usePlanHub';
import { usePlanOrigin } from '@/features/plan-hub/hooks/usePlanOrigin';
import { usePlanChildCreate } from '@/features/plan-hub/hooks/usePlanChildCreate';
import { usePlanHubMode } from '@/features/plan-hub/hooks/usePlanHubMode';
import { usePlanAdvancedView } from '@/features/plan-hub/hooks/usePlanAdvancedView';
import { useSimpleChapters } from '@/features/plan-hub/hooks/useSimpleChapters';
import { SimpleChapterList } from '@/features/plan-hub/components/SimpleChapterList';
import type { CameraFocusTarget, PlanOverlayRef } from '@/features/plan-hub/types';
import {
  LaneFlowView,
  PlanCanvas,
  PlanDrawer,
  PlanEmptyState,
  PlanToolbar,
  UnplannedTray,
} from '@/features/plan-hub/components';
import type { PlanViewMode } from '@/features/plan-hub/components/PlanToolbar';

export function PlanHubPanel(props: IDockviewPanelProps) {
  useStudioPanel('plan-hub', props.api);
  const { t } = useTranslation('studio');
  const { bookId, openPanel, focusManuscriptUnit } = useStudioHost();
  const { accessToken } = useAuth();
  const qc = useQueryClient();
  // View mode FIRST — it decides whether usePlanHub auto-expands the lane-flow hierarchy. Advanced
  // ⇒ open the first roots by default (mockup "root fix 2"); Simple ⇒ never (Simple renders a plain
  // list and must not fire a chapter-window fetch). Per-user setting (mirrors MotifSimpleMode).
  const mode = usePlanHubMode(accessToken);
  // Advanced sub-view: the navigable React Flow GRAPH (default) vs the readable LANE-flow view.
  const advView = usePlanAdvancedView(accessToken);
  // Auto-expand the lane hierarchy only when the LANE view will actually render it (Advanced + lane).
  // The graph loads windows on demand as arcs expand, so it doesn't want the bounded pre-seed.
  const view = usePlanHub(bookId, { autoExpandArcs: !mode.simple && !advView.graph });
  // The structure origin — the empty state's primary verb (spec 2026-07-17-studio-structure-origin).
  const origin = usePlanOrigin(bookId, accessToken);
  // Bug A — build the hierarchy DOWN from a selected node (+Chapter on an arc, +Scene on a chapter).
  // Both need a resolved Work's project_id; +Chapter also needs the book's own language for the new
  // book-service chapter (never hardcode 'en' — this is a multilingual platform).
  const workRes = useWorkResolution(bookId, accessToken);
  const projectId = workRes.data?.work?.project_id ?? null;
  const bookInfo = useQuery({
    queryKey: ['book', bookId],
    queryFn: () => booksApi.getBook(accessToken!, bookId),
    enabled: !!accessToken && !!bookId,
  });
  const originalLanguage = bookInfo.data?.original_language ?? 'en';
  const childCreate = usePlanChildCreate(bookId, projectId, accessToken, originalLanguage);

  const simpleChapters = useSimpleChapters(bookId, accessToken, mode.simple);
  // The "Write a new chapter" door: create a book chapter, then open it in the editor. This is the
  // content-first entry the pantser + newcomer both said was missing — no arc choice required.
  const writeChapter = useMutation({
    mutationFn: () => booksApi.createChapterEditor(accessToken!, bookId, { original_language: originalLanguage, title: '' }),
    onSuccess: (created) => {
      void qc.invalidateQueries({ queryKey: ['plan-hub', 'simple-chapters', bookId] });
      if (created?.chapter_id) focusManuscriptUnit(created.chapter_id);
    },
  });
  // Simple-mode CRUD — the edit/delete the panel named as missing ("only add and view"). Rename PATCHes
  // the book chapter's title; delete trashes it (soft, restorable). Both refetch the windowed list.
  const invalidateSimple = () => void qc.invalidateQueries({ queryKey: ['plan-hub', 'simple-chapters', bookId] });
  const renameChapter = useMutation({
    mutationFn: (v: { chapterId: string; title: string }) =>
      booksApi.patchChapter(accessToken!, bookId, v.chapterId, { title: v.title }),
    onSuccess: invalidateSimple,
  });
  const deleteChapter = useMutation({
    mutationFn: (chapterId: string) => booksApi.trashChapter(accessToken!, bookId, chapterId),
    onSuccess: invalidateSimple,
  });

  // H2.6 — the editor's active chapter (book-service chapter_id) off the bus. Map it to the Hub node
  // whose loaded content carries that chapterId; null when nothing's open or its window isn't loaded.
  // The editor's active chapter (book-service chapter_id) off the bus. The lane-flow cards match it
  // directly (each carries its chapterId); the GRAPH needs the mapped outline-node id for its
  // "you are here" highlight, so both forms are kept.
  const activeChapterId = useStudioBusSelector((s) => s.activeChapterId);
  const activeNodeId = useMemo(() => {
    if (!activeChapterId) return null;
    const hit = Object.entries(view.nodeContent).find(
      ([, c]) => c.kind === 'chapter' && c.chapterId === activeChapterId,
    );
    return hit ? hit[0] : null;
  }, [activeChapterId, view.nodeContent]);

  // PH18 deep-links — a problem ref opens its OWNING lens, FOCUSED on the offending row. Routed
  // through openPanel, never navigate() (PH24/DOCK-7).
  //   canon  → focus the RULE (`canon_rule.id`), which the panel's critic lane keys on, PLUS the
  //            node's chapter, which its entity-continuity lane keys on. The two lanes answer
  //            different questions and neither id alone reaches both.
  //   thread → focus the THREAD id directly (narrative_thread.id IS what the promises panel lists)
  // Recorded in RUN-STATE §6 as D-04 (PO approved option B: surface the rule-keyed lane).
  const openRef = useCallback(
    (ref: PlanOverlayRef, nodeId: string) => {
      if (ref.kind === 'thread') {
        openPanel('quality-promises', { focus: true, params: { bookId, focusThreadId: ref.id } });
        return;
      }
      const chapterId = view.nodeContent[nodeId]?.chapterId ?? null;
      openPanel('quality-canon', {
        focus: true,
        params: { bookId, focusRuleId: ref.id, focusChapterId: chapterId },
      });
    },
    [openPanel, bookId, view.nodeContent],
  );

  // ── PH15 toolbar state ──────────────────────────────────────────────────────────────────────
  const [search, setSearch] = useState('');
  const [fitSignal, setFitSignal] = useState(0);
  // PH22 ✅ P-10: v1 is narrative-only. The state exists (and the other two buttons are visible +
  // disabled) so the mode is a real, discoverable concept rather than a silently absent one.
  const [viewMode, setViewMode] = useState<PlanViewMode>('narrative');

  // A FIND, not a filter: matched cards are RINGED and everything stays exactly where it is (PH14 —
  // an insert must shift, never reshuffle; the same holds for the lane-flow view). Empty query ⇒
  // undefined ⇒ the cards render no find state at all.
  const matchedIds = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return undefined;
    const hits = new Set<string>();
    for (const [id, c] of Object.entries(view.nodeContent)) {
      if (c.title?.toLowerCase().includes(q)) hits.add(id);
    }
    return hits;
  }, [search, view.nodeContent]);

  // OQ-5 camera — a focus REQUEST (nodeId + monotonically bumped seq). The GRAPH pans to it; the LANE
  // view ignores focusTarget and instead relies on the select + ancestor-expand (so the card is on
  // screen). Doing all three makes a rail focus work in either sub-view.
  const [focusTarget, setFocusTarget] = useState<CameraFocusTarget | null>(null);
  const { select, expandAncestorsOf } = view;
  const focusNode = useCallback(
    (nodeId: string) => {
      expandAncestorsOf(nodeId);
      setFocusTarget((prev) => ({ nodeId, seq: (prev?.seq ?? 0) + 1 }));
      select(nodeId);
    },
    [select, expandAncestorsOf],
  );
  const planFocus = useStudioBusSelector((s) => s.planFocusSeq);
  const planFocusNodeId = useStudioBusSelector((s) => s.planFocusNodeId);
  const lastPlanFocus = useRef<number | undefined>(planFocus);
  useEffect(() => {
    if (planFocus === undefined || planFocus === lastPlanFocus.current) return;
    lastPlanFocus.current = planFocus;
    if (planFocusNodeId) focusNode(planFocusNodeId);
  }, [planFocus, planFocusNodeId, focusNode]);

  // The Simple | Advanced mode toggle — shown in BOTH views so a writer can always switch. Simple is
  // a plain chapter list (content-first); Advanced is the lane canvas (structure-first).
  const modeToggle = (
    <div className="flex flex-shrink-0 items-center gap-3 border-b bg-muted/20 px-3 py-1.5">
      {/* book title (mockup `.book`) — the surface's subject, so the writer always knows which book */}
      {bookInfo.data?.title && (
        <span data-testid="plan-hub-book-title" className="min-w-0 truncate font-serif text-sm font-semibold">
          {bookInfo.data.title}
        </span>
      )}
      <span className="flex-1" />
      <span className="inline-flex overflow-hidden rounded-full border text-[11px]">
        <button
          type="button"
          data-testid="plan-hub-mode-simple"
          aria-pressed={mode.simple}
          onClick={() => mode.setSimple(true)}
          className={`px-3 py-1 font-medium ${mode.simple ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:text-foreground'}`}
        >
          {t('planHub.mode.simple', 'Simple')}
        </button>
        <button
          type="button"
          data-testid="plan-hub-mode-advanced"
          aria-pressed={!mode.simple}
          onClick={() => mode.setSimple(false)}
          className={`px-3 py-1 font-medium ${!mode.simple ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:text-foreground'}`}
        >
          {t('planHub.mode.advanced', 'Advanced')}
        </button>
      </span>
      {/* Advanced sub-view: GRAPH (zoom/pan/drag — the navigable canvas) vs LANE (the readable flow).
          Only meaningful in Advanced. */}
      {!mode.simple && (
        <span className="inline-flex overflow-hidden rounded-full border text-[11px]">
          <button
            type="button"
            data-testid="plan-hub-adv-graph"
            aria-pressed={advView.graph}
            onClick={() => advView.setGraph(true)}
            className={`px-3 py-1 font-medium ${advView.graph ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:text-foreground'}`}
            title={t('planHub.adv.graphHint', 'Graph — zoom, pan and drag to move (best for a large structure)')}
          >
            {t('planHub.adv.graph', 'Graph')}
          </button>
          <button
            type="button"
            data-testid="plan-hub-adv-lane"
            aria-pressed={!advView.graph}
            onClick={() => advView.setGraph(false)}
            className={`px-3 py-1 font-medium ${!advView.graph ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:text-foreground'}`}
            title={t('planHub.adv.laneHint', 'Lane — readable wrapping cards (no zoom)')}
          >
            {t('planHub.adv.lane', 'Lane')}
          </button>
        </span>
      )}
      {/* cost (mockup `.cost`) — editing structure makes NO model calls, so it is genuinely free. A
          truthful $0.00 (not a fabricated model spend); the tooltip says why. */}
      <span
        data-testid="plan-hub-cost"
        className="flex-shrink-0 font-mono text-[11px] text-muted-foreground"
        title={t('planHub.costHint', 'Editing structure makes no model calls.')}
      >
        <span className="font-medium text-[hsl(var(--success))]">$0.00</span>
      </span>
    </div>
  );

  // SIMPLE MODE — the default. A linear chapter list + one "Write a new chapter" door. It reads book
  // chapters directly (not the plan shell), so it renders regardless of plan-shell load state — the
  // branch sits ABOVE the plan-shell guards on purpose.
  if (mode.simple) {
    return (
      <div data-testid="studio-plan-hub-panel" className="flex h-full w-full flex-col">
        {modeToggle}
        <SimpleChapterList
          chapters={simpleChapters.chapters}
          total={simpleChapters.total}
          loading={simpleChapters.loading}
          error={simpleChapters.error}
          hasMore={simpleChapters.hasMore}
          loadMore={simpleChapters.loadMore}
          loadingMore={simpleChapters.loadingMore}
          onOpenChapter={(chapterId) => focusManuscriptUnit(chapterId)}
          onWriteNew={accessToken ? () => writeChapter.mutate() : null}
          writing={writeChapter.isPending}
          onRename={accessToken ? (chapterId, title) => renameChapter.mutate({ chapterId, title }) : null}
          onDelete={accessToken ? (chapterId) => deleteChapter.mutate(chapterId) : null}
          mutating={renameChapter.isPending || deleteChapter.isPending}
          onAiDraft={() => openPanel('planner', { focus: true })}
          onGoAdvanced={() => mode.setSimple(false)}
        />
      </div>
    );
  }

  if (view.error) {
    return (
      <div
        data-testid="studio-plan-hub-panel"
        className="flex h-full w-full items-center justify-center p-4 text-sm text-destructive"
      >
        {view.error}
      </div>
    );
  }

  // Cold open — the shell has not landed yet. Without this the Hub rendered an EMPTY CANVAS while
  // loading, which is indistinguishable from a book with no plan: the user sees "nothing here" and
  // has no idea whether that is the answer or the question. (Ordered before `specEmpty` on purpose —
  // "still loading" must win over "nothing found".)
  if (view.loading && view.layout.lanes.length === 0 && view.layout.nodes.length === 0) {
    return (
      <div
        data-testid="studio-plan-hub-panel"
        className="flex h-full w-full items-center justify-center p-4 text-sm text-muted-foreground"
      >
        <span data-testid="plan-hub-loading">{t('planHub.loading', 'Loading the plan…')}</span>
      </div>
    );
  }

  // PH21 — the book has no spec at all. Offer the honest verbs instead of a blank canvas.
  // `specEmpty` is false until BOTH reads have answered, so this never flashes over a book whose plan
  // simply hasn't loaded (absent ≠ empty). Verb 3 opens the PlanForge panel via the host — zero
  // navigate() (PH24/DOCK-7).
  //
  // The ORIGIN verb (spec 2026-07-17-studio-structure-origin) is the primary: it is the only one that
  // works on an empty book, and it is the Studio's exit from the zero-state dead loop. `hasChapters`
  // is what lets Extract honour PH7 for real — proven upfront, so it renders disabled-with-reason
  // instead of failing after a click.
  if (view.specEmpty) {
    return (
      <div data-testid="studio-plan-hub-panel" className="flex h-full w-full flex-col">
        {modeToggle}
        <div className="min-h-0 flex-1">
        <PlanEmptyState
          onStartArc={accessToken ? (title) => void origin.start(title) : null}
          creatingArc={origin.creating}
          arcError={origin.error}
          onExtract={view.extract.run}
          hasChapters={view.chapters.length > 0}
          onPlanFromScratch={() => openPanel('planner', { focus: true })}
          extracting={view.extract.extracting}
          result={view.extract.result}
          error={view.extract.error}
        />
        </div>
      </div>
    );
  }

  // The selected node's kind routes the drawer's facet set + which backend it reads (arc/saga from
  // the shell, chapter/scene via getNode). nodeContent is keyed by node id for every drawn node.
  const selectedKind = view.selectedId ? view.nodeContent[view.selectedId]?.kind ?? null : null;

  return (
    <div data-testid="studio-plan-hub-panel" className="flex h-full w-full min-h-0 flex-col">
      {modeToggle}
      <div className="flex min-h-0 flex-1">
      {/* PH25/OQ-6 — the Plan navigator is NOT a column in here. It is an ACTIVITY BAR rail (it and
          the canvas are two densities of one dataset), and OQ-6 rejects a third in-panel list as a
          duplicate of it. It reaches us over the bus (`planFocusNode`, subscribed above). */}
      {/* center column: TOOLBAR + graph + the H3 drawer overlay, with the PH21 tray docked beneath.
          The canvas gets `relative` so the drawer's `absolute right-0` pins to THAT region and not
          the window (the dockview fixed-positioning bug); the toolbar and tray sit OUTSIDE it, in
          normal flow, so neither overlaps the drawer. */}
      <div className="flex min-w-0 flex-1 flex-col">
      <PlanToolbar
        search={search}
        onSearch={setSearch}
        onFit={() => setFitSignal((n) => n + 1)}
        onProblems={() => openPanel('quality', { focus: true, params: { bookId } })}
        // OQ-7 ✅ P-13: "Ask AI" is NOT a canvas-native plan agent — it is the Compose chat, opened
        // with the current selection as its subject. Null with nothing selected: there'd be no
        // subject to ask ABOUT, and the button says so rather than opening an empty chat.
        onAskAi={
          view.selectedId
            ? () =>
                openPanel('compose', {
                  focus: true,
                  params: { bookId, subjectNodeId: view.selectedId },
                })
            : null
        }
        // Manual create wired to the existing backend (missing GUI ≠ missing feature). A created arc
        // is selected so the drawer can rename it in place — no modal. Sub-arc nests under the
        // selection only when that selection is itself an arc/saga (the model's parent rule).
        onAddArc={
          accessToken
            ? () => {
                void origin
                  .start(t('planHub.empty.untitledArc', 'Untitled arc'))
                  .then((arc) => arc && view.select(arc.id));
              }
            : null
        }
        onAddSubArc={
          accessToken && view.selectedId && (selectedKind === 'arc' || selectedKind === 'saga')
            ? () => {
                const parentId = view.selectedId!;
                void origin
                  .start(t('planHub.empty.untitledArc', 'Untitled arc'), parentId)
                  .then((arc) => arc && view.select(arc.id));
              }
            : null
        }
        creatingArc={origin.creating}
        view={viewMode}
        onView={setViewMode}
        problemCount={view.problemTotal}
      />
      <div className="relative min-w-0 flex-1">
        {/* ADVANCED has two sub-views (a per-user setting). GRAPH = the React Flow canvas (zoom, pan,
            drag-to-move, scene links — the navigable tool for a large structure). LANE = the sealed
            lane-flow redesign (design-drafts/plan-hub-redesign/index.html): readable wrapping cards,
            inset sub-arcs, no zoom. Both share the SAME drawer, toolbar, tray, and create routes. */}
        {advView.graph ? (
          <PlanCanvas
            layout={view.layout}
            edges={view.edges}
            overlay={view.overlay}
            conformance={view.conformance}
            unionState={view.unionState}
            nodeContent={view.nodeContent}
            selectedId={view.selectedId}
            onSelect={view.select}
            onToggleArc={view.toggleArc}
            onToggleChapter={view.toggleChapter}
            activeNodeId={activeNodeId}
            focusTarget={focusTarget}
            onMoveChapter={view.moveChapterToArc}
            onMoveScene={view.moveSceneToChapter}
            onMoveArc={view.moveArcTo}
            onReorderChapter={view.reorderChapter}
            arcPagination={view.arcPagination}
            onLoadMoreArc={view.loadMoreArc}
            onOpenRef={openRef}
            onLinkScenes={view.linkScenes}
            onUnlinkScenes={view.unlinkScenes}
            resolveEntity={view.resolveEntity}
            fitSignal={fitSignal}
            matchedIds={matchedIds}
            busy={view.moving}
          />
        ) : (
          <LaneFlowView
            laneTree={view.laneTree}
            unassigned={view.laneUnassigned}
            arcOptions={view.arcOptions}
            onMoveChapterToArc={accessToken ? view.moveChapterToArc : null}
            arcPagination={view.arcPagination}
            selectedId={view.selectedId}
            activeChapterId={activeChapterId ?? null}
            onSelect={view.select}
            onToggleArc={view.toggleArc}
            onToggleChapter={view.toggleChapter}
            onLoadMoreArc={view.loadMoreArc}
            onAddChapter={
              accessToken && projectId
                ? (arcId) => void childCreate.addChapterUnderArc(arcId).then((n) => n && view.select(n.id))
                : null
            }
            onAddScene={
              accessToken && projectId
                ? (chapterNodeId, bookChapterId) =>
                    void childCreate.addSceneUnderChapter(chapterNodeId, bookChapterId).then((n) => n && view.select(n.id))
                : null
            }
            onAddSubArc={
              accessToken
                ? (parentArcId) =>
                    void origin
                      .start(t('planHub.empty.untitledArc', 'Untitled arc'), parentArcId)
                      .then((arc) => arc && view.select(arc.id))
                : null
            }
            addingChild={childCreate.creating || origin.creating}
            childError={childCreate.error || origin.error}
            matchedIds={matchedIds}
            fitSignal={fitSignal}
          />
        )}
        {/* GRAPH mode surfaces arc-less chapters (drag them into a lane) via a HUD count — the graph
            renders them in its own strip. LANE mode renders them as a selectable "Unassigned" group.  */}
        {advView.graph && view.layout.unassigned.length > 0 && (
          <div
            data-testid="plan-hub-unassigned-notice"
            className="pointer-events-none absolute left-3 top-3 z-20 rounded-md border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-xs text-amber-700 shadow"
          >
            {t('planHub.node.unassignedFlow', {
              count: view.layout.unassigned.length,
              defaultValue: '{{count}} chapter not in any storyline yet',
              defaultValue_other: '{{count}} chapters not in any storyline yet',
            })}
          </div>
        )}
        {/* A failed move (incl. the 412 "changed elsewhere — reloaded" OCC recovery) is surfaced,
            never swallowed — the canvas has already re-synced from the server underneath it. */}
        {/* A failed move (incl. the 412 "changed elsewhere — reloaded" OCC recovery) is surfaced,
            never swallowed — the canvas has already re-synced from the server underneath it. */}
        {view.moveError && (
          <div
            data-testid="plan-hub-move-error"
            className="pointer-events-none absolute bottom-3 left-1/2 z-20 -translate-x-1/2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-1.5 text-xs text-destructive shadow"
          >
            {view.moveError}
          </div>
        )}
        {/* One-level UNDO of the last successful move. It matters most for Row-3, which mutates the
            actual manuscript order — a mis-aimed drag should be one click to reverse, not a hunt
            through the chapter list. Hidden while a move is in flight (the inverse would be aimed at
            a layout the server is about to replace). */}
        {view.undo && !view.moveError && !view.moving && (
          <div className="absolute bottom-3 left-1/2 z-20 flex -translate-x-1/2 items-center gap-2 rounded-md border bg-background/95 px-3 py-1.5 text-xs shadow">
            <span className="text-muted-foreground">{view.undo.label}</span>
            <button
              type="button"
              data-testid="plan-hub-undo"
              className="font-medium text-primary underline-offset-2 hover:underline"
              onClick={() => view.undo?.run()}
            >
              {t('planHub.undo', 'Undo')}
            </button>
          </div>
        )}
        {/* Always mounted — PlanDrawer self-hides on a null selection (never conditionally unmount a
            stateful child). onClose clears the selection, which also drops the rail/canvas highlight. */}
        <PlanDrawer
          selectedId={view.selectedId}
          kind={selectedKind}
          bookId={bookId}
          onClose={() => view.select(null)}
          overlay={view.overlay}
          onOpenRef={openRef}
          writes={view.nodeWrites}
          chapters={view.chapters}
          onOpenInEditor={(chapterId) => focusManuscriptUnit(chapterId)}
          // Bug A — the contextual create the drawer never had: +Chapter under an arc, +Scene under a
          // chapter. Disabled (null) until a Work exists. The created node is selected so the drawer
          // re-targets it for inline rename — same create-then-name flow as the toolbar's +Arc.
          childCreate={
            accessToken && projectId
              ? {
                  busy: childCreate.creating,
                  error: childCreate.error,
                  addChapter: (arcId: string) =>
                    void childCreate.addChapterUnderArc(arcId).then((n) => n && view.select(n.id)),
                  addScene: (chapterNodeId: string, bookChapterId: string) =>
                    void childCreate.addSceneUnderChapter(chapterNodeId, bookChapterId).then((n) => n && view.select(n.id)),
                }
              : null
          }
        />
      </div>

        {/* Every partial truth the canvas is currently showing, said out loud. The Hub degrades in
            several ways (the manuscript join dead ⇒ no written/not-written treatment; refs capped;
            the coverage diff uncomputable) and each used to degrade SILENTLY — showing less, and
            looking exactly like a healthy canvas showing less. */}
        {view.notices.length > 0 && (
          <ul
            data-testid="plan-hub-notices"
            className="border-t border-amber-500/30 bg-amber-500/5 px-3 py-1 text-xs text-amber-700"
          >
            {view.notices.map((n) => (
              <li key={n} data-testid="plan-hub-notice">
                {n}
              </li>
            ))}
          </ul>
        )}

        {/* PH21 — manuscript chapters no spec node covers. Drift made visible, never auto-planned.
            Self-hides when there are none AND we know it; renders "unknown" when the coverage diff
            could not be computed. A row opens the chapter in the EDITOR — the unplanned chapter has
            no spec node to select, so the only truthful destination is where it actually lives. */}
        <UnplannedTray
          chapters={view.unplanned}
          total={view.unplannedCount}
          onOpenChapter={(chapterId) => focusManuscriptUnit(chapterId)}
        />
      </div>
      </div>
    </div>
  );
}
