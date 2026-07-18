// 24 PH15 / PH22 / OQ-7 — the Hub toolbar.
//
// PH22 is explicit and RATIFIED (P-10): "v1 ships narrative mode only — timeline/worldmap each ship
// in a later phase, BUTTONS VISIBLE BUT DISABLED." That is PH7's visible-fallback: a capability the
// product intends must be discoverable and honestly unavailable, not absent. Hiding them would make
// the two look like they were never planned; enabling them would be a dead button.
//
// "Ask AI about this plan" (OQ-7) is ratified P-13: it is NOT a canvas-native plan agent — it is the
// Compose chat, opened with the current selection as its subject. So the toolbar's job is to open
// that panel with a ref, nothing more.
import { useTranslation } from 'react-i18next';

export type PlanViewMode = 'narrative' | 'timeline' | 'worldmap';

export interface PlanToolbarProps {
  search: string;
  onSearch: (q: string) => void;
  /** Fit the whole graph in the viewport. */
  onFit: () => void;
  /** Open the problems lens (the Quality hub) for this book. */
  onProblems: () => void;
  /** OQ-7/P-13 — Compose chat, with the current selection as its subject. Null ⇒ nothing selected. */
  onAskAi: (() => void) | null;
  /** Create a top-level arc. Null ⇒ the caller can't offer it (no EDIT grant / no token). The GUI for
   *  a capability the backend already had (POST /books/{id}/arcs) — missing GUI ≠ missing feature. */
  onAddArc: (() => void) | null;
  /** Create a sub-arc under the SELECTED arc/saga. Null ⇒ selection isn't an arc, so there's no
   *  parent to nest under — disabled-with-reason, never a dead button (PH7). */
  onAddSubArc: (() => void) | null;
  creatingArc: boolean;
  view: PlanViewMode;
  onView: (v: PlanViewMode) => void;
  /** Total problems across the book (canon + threads), for the toolbar counter. */
  problemCount: number;
}

const btn =
  'rounded border px-2 py-1 text-xs font-medium hover:bg-accent disabled:cursor-not-allowed disabled:opacity-40';

export function PlanToolbar({
  search,
  onSearch,
  onFit,
  onProblems,
  onAskAi,
  onAddArc,
  onAddSubArc,
  creatingArc,
  view,
  onView,
  problemCount,
}: PlanToolbarProps) {
  const { t } = useTranslation('studio');

  return (
    <div
      data-testid="plan-hub-toolbar"
      className="flex flex-wrap items-center gap-1.5 border-b bg-muted/20 px-2 py-1"
    >
      <input
        data-testid="plan-hub-search"
        value={search}
        onChange={(e) => onSearch(e.target.value)}
        placeholder={t('planHub.toolbar.search', 'Filter nodes…')}
        className="w-40 rounded border bg-background px-1.5 py-1 text-xs"
      />

      {/* Manual structure authoring — the GUI the canvas never had for a route the backend always
          did (POST /books/{id}/arcs). A new arc is created "Untitled" and selected, so it is renamed
          IN PLACE via the drawer — no modal (the killed Spine's one good instinct). Sub-arc nests
          under the selected arc via parent_arc_id; disabled-with-reason when the selection can't be a
          parent. Chapters/scenes are NOT peers here — a scene needs a chapter_id and a chapter is
          book-service's to create; those hang off their parents contextually, not on this bar. */}
      <button
        type="button"
        data-testid="plan-hub-add-arc"
        onClick={() => onAddArc?.()}
        disabled={!onAddArc || creatingArc}
        title={onAddArc ? t('planHub.toolbar.addArcHint', 'Add a top-level arc') : t('planHub.toolbar.addArcNoGrant', 'You need edit access to add arcs')}
        className={btn}
      >
        {creatingArc ? t('planHub.toolbar.addingArc', '+ Arc…') : t('planHub.toolbar.addArc', '+ Arc')}
      </button>
      <button
        type="button"
        data-testid="plan-hub-add-subarc"
        onClick={() => onAddSubArc?.()}
        disabled={!onAddSubArc || creatingArc}
        title={onAddSubArc ? t('planHub.toolbar.addSubArcHint', 'Add a sub-arc under the selected arc') : t('planHub.toolbar.addSubArcHint2', 'Select an arc to nest a sub-arc under it')}
        className={btn}
      >
        {t('planHub.toolbar.addSubArc', '+ Sub-arc')}
      </button>

      <span className="mx-1 h-4 w-px bg-border" />

      <button type="button" data-testid="plan-hub-fit" onClick={onFit} className={btn}>
        {t('planHub.toolbar.fit', 'Fit')}
      </button>

      <button
        type="button"
        data-testid="plan-hub-problems"
        onClick={onProblems}
        className={btn}
        title={t('planHub.toolbar.problems', 'Problems')}
      >
        {t('planHub.toolbar.problems', 'Problems')}
        {problemCount > 0 && (
          <span
            data-testid="plan-hub-problem-count"
            className="ml-1 rounded bg-destructive/15 px-1 text-destructive"
          >
            {problemCount}
          </span>
        )}
      </button>

      <button
        type="button"
        data-testid="plan-hub-ask-ai"
        onClick={() => onAskAi?.()}
        disabled={!onAskAi}
        title={
          onAskAi
            ? undefined
            : t('planHub.toolbar.askAiHint', 'Select a node to ask about it')
        }
        className={btn}
      >
        {t('planHub.toolbar.askAi', 'Ask AI')}
      </button>

      <span className="mx-1 h-4 w-px bg-border" />

      {/* PH22 — the three view modes. Only `narrative` is built (P-10 ✅). The other two are VISIBLE
          and DISABLED, on purpose: the product intends them, so they must be discoverable and
          honestly unavailable rather than silently absent. */}
      {(['narrative', 'timeline', 'worldmap'] as const).map((m) => {
        const built = m === 'narrative';
        return (
          <button
            key={m}
            type="button"
            data-testid={`plan-hub-view-${m}`}
            aria-pressed={view === m}
            disabled={!built}
            title={built ? undefined : t('planHub.toolbar.viewSoon', 'Coming in a later phase')}
            onClick={() => built && onView(m)}
            className={`${btn} ${view === m ? 'bg-accent' : ''}`}
          >
            {t(`planHub.toolbar.view${m[0].toUpperCase()}${m.slice(1)}`, m)}
          </button>
        );
      })}
    </div>
  );
}
