// Manuscript navigator (#02) — the Side Bar's arc→chapter→scene tree.
//
// Virtualized (@tanstack/react-virtual) so a 10k-chapter book renders only the visible rows.
// Chapters page in via cursor; a Work's arcs/scenes lazy-load on expand. Selecting a chapter/
// scene calls onSelect — the dock wiring lands with #03 (Debt #1); until then it highlights.
//
// Visual parity with design-drafts/screens/studio/screen-manuscript-navigator.html: a header
// with New/Collapse-all/Reload actions, roman-numeral arcs + child-count badges, zero-padded
// chapter numbers, a selected-row accent bar, scene status dots, a shimmer skeleton on lazy
// load, and a footer window-position readout.
//
// Jump/search: the box is SERVER-BACKED (useManuscriptJump) — it queries the whole book
// (outline search for a Work, book-service chapter search for imports), so it reaches nodes
// NOT yet lazy-loaded into the tree (the v1 client-filter's blind spot). Typing switches the
// body from the tree to a flat result list; clearing returns to the tree.
import { useCallback, useEffect, useMemo, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useVirtualizer } from '@tanstack/react-virtual';
import { ChevronRight, ChevronsDownUp, FolderPlus, Loader2, PanelLeftClose, Pencil, Plus, RotateCw, Search, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useManuscriptTree } from './useManuscriptTree';
import { useManuscriptJump } from './useManuscriptJump';
import { jumpResultToNode, type ManuscriptNode } from './types';

interface Props {
  bookId: string;
  token: string | null;
  /** The currently selected node id (highlight). */
  selectedId?: string | null;
  /** Called when a chapter/scene row is chosen. Dock wiring is #03 (Debt #1). */
  onSelect?: (node: ManuscriptNode) => void;
  /** New-chapter action (header +). When absent the button renders disabled (create flow = Debt). */
  onNewChapter?: () => void;
  /** Collapse the whole Side Bar (studio chrome). When provided the navigator's own header hosts
   * the button, so the Side Bar doesn't render a duplicate header above it. */
  onCollapseSidebar?: () => void;
}

const ROW_H = 26;

/** 1→I, 4→IV, … (arcs never exceed a few dozen, but the full converter is trivial + safe). */
function toRoman(n: number): string {
  if (n <= 0) return String(n);
  const table: Array<[number, string]> = [
    [1000, 'M'], [900, 'CM'], [500, 'D'], [400, 'CD'], [100, 'C'], [90, 'XC'],
    [50, 'L'], [40, 'XL'], [10, 'X'], [9, 'IX'], [5, 'V'], [4, 'IV'], [1, 'I'],
  ];
  let out = '';
  for (const [v, sym] of table) while (n >= v) { out += sym; n -= v; }
  return out;
}

export function ManuscriptNavigator({ bookId, token, selectedId, onSelect, onNewChapter, onCollapseSidebar }: Props) {
  const { t } = useTranslation('studio');
  const {
    source, rows, total, counts, error,
    toggleExpand, loadMore, collapseAll, reload,
    createAct, renameAct, trashAct, moveChapterToAct,
  } = useManuscriptTree(bookId, token);
  const jump = useManuscriptJump(bookId, token);
  const parentRef = useRef<HTMLDivElement>(null);
  // S-02 — the chapter id currently dragged onto an act (native HTML5 DnD, trusted user drag).
  const dragChapterId = useRef<string | null>(null);

  // S-02 act affordances. prompt/confirm keep this navigator edit minimal + immediately operable
  // (inline editors are a later polish); each awaits a mutator that reloads the grouped tree.
  const onNewAct = useCallback(() => {
    const title = window.prompt(t('manuscript.newActPrompt', { defaultValue: 'Name the new act' }))?.trim();
    if (title != null) void createAct(title);
  }, [createAct, t]);
  const onRenameAct = useCallback((id: string, current: string) => {
    const title = window.prompt(t('manuscript.renameActPrompt', { defaultValue: 'Rename act' }), current)?.trim();
    if (title != null) void renameAct(id, title);
  }, [renameAct, t]);
  const onTrashAct = useCallback((id: string) => {
    if (window.confirm(t('manuscript.trashActConfirm', { defaultValue: 'Trash this act? Its chapters stay in the book, just un-filed.' }))) void trashAct(id);
  }, [trashAct, t]);

  // 1-based ordinal per top-level arc → roman numeral label (ARC I / II / …). Computed over the
  // full loaded row list (not the virtual window) so it's stable as you scroll.
  const arcOrdinal = useMemo(() => {
    const map = new Map<string, number>();
    let n = 0;
    for (const r of rows) {
      if (r.type === 'node' && r.depth === 0 && r.node.kind === 'arc') map.set(r.node.id, ++n);
    }
    return map;
  }, [rows]);

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ROW_H,
    overscan: 12,
  });
  const vItems = virtualizer.getVirtualItems();

  // Infinite paging: when a `more` row is rendered, fetch its next page (guarded in the hook so
  // it never double-fetches). Skipped while searching (the tree isn't the visible body then).
  useEffect(() => {
    if (jump.active) return;
    for (const vi of vItems) {
      const row = rows[vi.index];
      if (row?.type === 'more') loadMore(row.parentKey, row.parentNodeId);
    }
  }, [vItems, rows, loadMore, jump.active]);

  // Footer window readout (VS Code "win 100–140 / N"). 1-based, from the virtual range.
  const winStart = vItems.length ? vItems[0].index + 1 : 0;
  const winEnd = vItems.length ? vItems[vItems.length - 1].index + 1 : 0;

  // Footer totals (mockup .nav-foot: "10,342 ch · 48,120 sc"). Outline → arc·ch·sc; a flat
  // import → chapters only (no arcs/scenes). Localized thousands separators.
  const fmt = (n: number) => n.toLocaleString();
  const statParts: string[] = [];
  if (counts.arcs != null && counts.arcs > 0) statParts.push(t('manuscript.statArcs', { n: fmt(counts.arcs), defaultValue: '{{n}} arc' }));
  if (counts.chapters != null) statParts.push(t('manuscript.statChapters', { n: fmt(counts.chapters), defaultValue: '{{n}} ch' }));
  if (counts.scenes != null && counts.scenes > 0) statParts.push(t('manuscript.statScenes', { n: fmt(counts.scenes), defaultValue: '{{n}} sc' }));

  if (source === 'pending') {
    return <div data-testid="manuscript-nav" className="flex flex-1 items-center justify-center p-4 text-[11px] text-muted-foreground">
      <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />{t('manuscript.loading', { defaultValue: 'Loading…' })}
    </div>;
  }

  return (
    <div data-testid="manuscript-nav" className="flex min-h-0 flex-1 flex-col">
      {/* Header: title + actions (mockup .nav-head) */}
      <div className="flex h-[34px] flex-shrink-0 items-center justify-between border-b pl-3 pr-2 text-[10px] font-bold uppercase tracking-[0.06em] text-muted-foreground">
        <span>{t('manuscript.title', { defaultValue: 'Manuscript' })}</span>
        <div className="flex items-center gap-0.5">
          {/* S-02 — New act (manuscript part). Only meaningful for a manuscript-structured book
              (no composition Work); the outline owns the hierarchy when a Work exists. */}
          {source === 'chapters' && (
            <button
              type="button"
              data-testid="manuscript-part-new"
              onClick={onNewAct}
              title={t('manuscript.newAct', { defaultValue: 'New act' })}
              className="flex h-5 w-5 items-center justify-center rounded text-muted-foreground hover:bg-secondary hover:text-foreground"
            >
              <FolderPlus className="h-3.5 w-3.5" />
            </button>
          )}
          {/* Opens the PLAN (plan-hub), it does not create a chapter — structure authoring is a spec
              act and lives on the Plan rail (StudioSideBar's rail contract). The label changed with
              the behaviour on 2026-07-17: it read "New chapter" while being permanently disabled,
              which is the worst of both — a promise it never kept and couldn't. */}
          <button
            type="button"
            data-testid="manuscript-new"
            onClick={onNewChapter}
            disabled={!onNewChapter}
            title={t('manuscript.openPlan', { defaultValue: 'Plan this book' })}
            className="flex h-5 w-5 items-center justify-center rounded text-muted-foreground hover:bg-secondary hover:text-foreground disabled:pointer-events-none disabled:opacity-40"
          >
            <Plus className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            data-testid="manuscript-collapse"
            onClick={collapseAll}
            title={t('manuscript.collapseAll', { defaultValue: 'Collapse all' })}
            className="flex h-5 w-5 items-center justify-center rounded text-muted-foreground hover:bg-secondary hover:text-foreground"
          >
            <ChevronsDownUp className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            data-testid="manuscript-reload"
            onClick={reload}
            title={t('manuscript.reload', { defaultValue: 'Reload' })}
            className="flex h-5 w-5 items-center justify-center rounded text-muted-foreground hover:bg-secondary hover:text-foreground"
          >
            <RotateCw className="h-3.5 w-3.5" />
          </button>
          {onCollapseSidebar && (
            <>
              <span className="mx-0.5 h-3.5 w-px bg-border" />
              <button
                type="button"
                data-testid="manuscript-collapse-sidebar"
                onClick={onCollapseSidebar}
                title={t('sidebar.collapse', { defaultValue: 'Collapse' })}
                className="flex h-5 w-5 items-center justify-center rounded text-muted-foreground hover:bg-secondary hover:text-foreground"
              >
                <PanelLeftClose className="h-3.5 w-3.5" />
              </button>
            </>
          )}
        </div>
      </div>

      {/* Jump / search box (server-backed) */}
      <div className="flex-shrink-0 border-b p-2">
        <div className="flex h-7 items-center gap-1.5 rounded-md border bg-background px-2 text-xs text-muted-foreground">
          {jump.searching ? <Loader2 className="h-3 w-3 animate-spin" /> : <Search className="h-3 w-3" />}
          <input
            data-testid="manuscript-filter"
            value={jump.query}
            onChange={(e) => jump.setQuery(e.target.value)}
            placeholder={t('manuscript.filter', { defaultValue: 'Jump to chapter / scene…' })}
            className="min-w-0 flex-1 bg-transparent text-foreground outline-none placeholder:text-muted-foreground/60"
          />
          <span className="rounded border border-border px-1 font-mono text-[9px] leading-normal">↵</span>
        </div>
      </div>

      {error && !jump.active && <div className="px-3 py-1.5 text-[11px] text-amber-600">{error}</div>}

      <div ref={parentRef} data-testid="manuscript-scroll" className="min-h-0 flex-1 overflow-y-auto">
        {jump.active ? (
          /* ── Server search results (flat list across the WHOLE book) ─────────── */
          jump.results.length === 0 ? (
            <div className="p-4 text-center text-[11px] text-muted-foreground" data-testid="manuscript-results-empty">
              {jump.searching
                ? t('manuscript.searching', { defaultValue: 'Searching…' })
                : t('manuscript.noMatch', { defaultValue: 'No matches.' })}
            </div>
          ) : (
            <div data-testid="manuscript-results" className="py-1">
              {jump.results.map((r) => (
                <button
                  key={r.id}
                  type="button"
                  data-testid={`manuscript-result-${r.id}`}
                  onClick={() => onSelect?.(jumpResultToNode(r))}
                  className={cn(
                    'flex w-full items-center gap-2 px-3 py-1 text-left text-xs hover:bg-secondary',
                    selectedId === r.id && 'bg-primary/10 text-primary',
                  )}
                >
                  <span className={cn('h-1.5 w-1.5 flex-shrink-0 rounded-full',
                    r.kind === 'arc' ? 'bg-accent' : r.kind === 'scene' ? 'bg-border' : 'bg-muted-foreground/60')} />
                  <span className="flex min-w-0 flex-col">
                    <span className="truncate">{r.title}</span>
                    {r.path.length > 0 && (
                      <span className="truncate text-[10px] text-muted-foreground">{r.path.join(' › ')}</span>
                    )}
                  </span>
                </button>
              ))}
            </div>
          )
        ) : rows.length === 0 && !error ? (
          <div className="p-4 text-center text-[11px] text-muted-foreground">
            {t('manuscript.empty', { defaultValue: 'No chapters yet.' })}
          </div>
        ) : (
          /* ── Virtualized tree ───────────────────────────────────────────────── */
          <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
            {vItems.map((vi) => {
              const row = rows[vi.index];
              const style: React.CSSProperties = {
                position: 'absolute', top: 0, left: 0, right: 0, height: ROW_H,
                transform: `translateY(${vi.start}px)`,
              };

              if (row.type === 'skeleton') {
                return (
                  <div key={row.key} data-testid="manuscript-skeleton" style={{ ...style, paddingLeft: 10 + row.depth * 16 }}
                    className="flex items-center pr-3">
                    <span
                      className="h-2 animate-pulse rounded bg-secondary"
                      style={{ width: `${58 - (vi.index % 3) * 10}%` }}
                    />
                  </div>
                );
              }

              if (row.type === 'more') {
                return (
                  <button
                    key={`more-${row.parentKey}`}
                    type="button"
                    data-testid="manuscript-more"
                    onClick={() => loadMore(row.parentKey, row.parentNodeId)}
                    style={{ ...style, paddingLeft: 8 + row.depth * 16 }}
                    className="flex items-center gap-1.5 text-[11px] text-muted-foreground hover:text-foreground"
                  >
                    <Loader2 className="h-3 w-3 animate-spin" />
                    {t('manuscript.loadingMore', { defaultValue: 'Loading more…' })}
                  </button>
                );
              }

              const { node, depth, expanded, loading } = row;
              const selected = selectedId === node.id;
              const isArc = node.kind === 'arc';
              const isPart = node.kind === 'part';                       // S-02 act group header
              const isUnassigned = isPart && node.status === 'unassigned'; // the flat-manuscript bucket
              const isScene = node.kind === 'scene';
              const isChapter = node.kind === 'chapter';
              const isGroup = isArc || isPart; // an expandable group header (click toggles, not select)
              return (
                <div
                  key={node.id}
                  data-testid={`manuscript-row-${node.id}`}
                  role="treeitem"
                  aria-expanded={node.hasChildren ? expanded : undefined}
                  aria-selected={selected}
                  // S-02 drag-a-chapter-between-acts: chapters are draggable; act headers are drop
                  // targets → PATCH .../chapters/{id}/part (moveChapterToAct). Trusted HTML5 DnD.
                  draggable={isChapter}
                  onDragStart={isChapter ? (() => { dragChapterId.current = node.chapterId; }) : undefined}
                  onDragEnd={isChapter ? (() => { dragChapterId.current = null; }) : undefined}
                  onDragOver={isPart ? ((e) => e.preventDefault()) : undefined}
                  onDrop={isPart ? ((e) => {
                    e.preventDefault();
                    const cid = dragChapterId.current;
                    dragChapterId.current = null;
                    if (cid) void moveChapterToAct(cid, isUnassigned ? null : node.id);
                  }) : undefined}
                  onClick={() => (isGroup ? (node.hasChildren && toggleExpand(node.id)) : onSelect?.(node))}
                  style={{ ...style, paddingLeft: 4 + depth * 16 }}
                  className={cn(
                    'group/row flex cursor-pointer items-center gap-1 pr-2 text-xs',
                    selected ? 'bg-primary/10 text-primary' : 'hover:bg-secondary',
                    (isArc || isPart) && 'font-bold',
                    isArc && !selected && 'text-accent-foreground',
                    isUnassigned && !selected && 'text-amber-600',
                    isChapter && 'font-medium',
                    isScene && !selected && 'text-muted-foreground',
                  )}
                >
                  {/* selected-row accent bar (mockup .row.active::before) */}
                  {selected && <span className="pointer-events-none absolute left-0 top-0 h-full w-[2px] bg-primary" />}

                  {/* caret (expandable) / leaf spacer / scene dot */}
                  {node.hasChildren ? (
                    <button
                      type="button"
                      data-testid={`manuscript-caret-${node.id}`}
                      onClick={(e) => { e.stopPropagation(); toggleExpand(node.id); }}
                      className={cn('flex h-4 w-4 flex-shrink-0 items-center justify-center', (isArc || isPart) ? 'text-accent' : 'text-muted-foreground')}
                      aria-label={expanded ? 'collapse' : 'expand'}
                    >
                      {loading
                        ? <Loader2 className="h-3 w-3 animate-spin" />
                        : <ChevronRight className={cn('h-3 w-3 transition-transform', expanded && 'rotate-90')} />}
                    </button>
                  ) : (
                    <span className="flex h-4 w-4 flex-shrink-0 items-center justify-center">
                      {isScene && (
                        <span className={cn('h-1.5 w-1.5 rounded-full',
                          node.status === 'done' ? 'bg-success' : selected ? 'bg-primary' : 'bg-border')} />
                      )}
                    </span>
                  )}

                  {/* arc roman numeral / act tag / chapter number */}
                  {isArc && (
                    <span className="flex-shrink-0 font-mono text-[9px] text-accent">
                      {t('manuscript.arc', { defaultValue: 'ARC' })} {toRoman(arcOrdinal.get(node.id) ?? 0)}
                    </span>
                  )}
                  {isPart && !isUnassigned && (
                    <span className="flex-shrink-0 font-mono text-[9px] text-accent">
                      {t('manuscript.actTag', { defaultValue: 'ACT' })}
                    </span>
                  )}
                  {isChapter && node.number != null && (
                    <span className="w-9 flex-shrink-0 text-left font-mono text-[10px] text-muted-foreground/50">
                      {String(node.number).padStart(4, '0')}
                    </span>
                  )}

                  <span className="truncate">{node.title}</span>

                  {/* child-count badge: chapter → scenes, arc → chapters, act → chapters */}
                  {node.childCount != null && node.childCount > 0 && (
                    <span className={cn('flex-shrink-0 font-mono text-[9px]', isPart ? 'ml-1' : 'ml-auto', (isArc || isPart) ? 'text-accent' : 'text-muted-foreground')}>
                      {node.childCount}
                    </span>
                  )}

                  {/* S-02 act affordances (rename / trash) — real acts only, revealed on hover */}
                  {isPart && !isUnassigned && (
                    <span className="ml-auto flex flex-shrink-0 items-center gap-0.5 opacity-0 group-hover/row:opacity-100">
                      <button
                        type="button"
                        data-testid={`manuscript-part-rename-${node.id}`}
                        onClick={(e) => { e.stopPropagation(); onRenameAct(node.id, node.title); }}
                        title={t('manuscript.renameAct', { defaultValue: 'Rename act' })}
                        className="flex h-4 w-4 items-center justify-center rounded text-muted-foreground hover:text-foreground"
                      >
                        <Pencil className="h-3 w-3" />
                      </button>
                      <button
                        type="button"
                        data-testid={`manuscript-part-trash-${node.id}`}
                        onClick={(e) => { e.stopPropagation(); onTrashAct(node.id); }}
                        title={t('manuscript.trashAct', { defaultValue: 'Trash act' })}
                        className="flex h-4 w-4 items-center justify-center rounded text-muted-foreground hover:text-destructive"
                      >
                        <Trash2 className="h-3 w-3" />
                      </button>
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Footer: whole-book totals (arc·ch·sc) + virtual window position (mockup .nav-foot) */}
      <div className="flex h-6 flex-shrink-0 items-center gap-2 border-t px-3 font-mono text-[10px] text-muted-foreground">
        {statParts.length > 0 && <span data-testid="manuscript-totals">{statParts.join(' · ')}</span>}
        {!jump.active && rows.length > 0 && (
          <span className="ml-auto text-muted-foreground/50" data-testid="manuscript-window">
            {t('manuscript.window', { defaultValue: 'win {{a}}–{{b}} / {{n}}', a: winStart, b: winEnd, n: rows.length })}
          </span>
        )}
      </div>
    </div>
  );
}
