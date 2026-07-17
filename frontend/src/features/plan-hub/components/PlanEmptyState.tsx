// 24 PH21 — the empty state: this book has NO spec at all (no arcs, no chapter nodes).
//
// The Hub NEVER synthesises a graph from the manuscript's chapters. Inferring structure is the
// DECOMPILER's explicit job, and doing it uninvited would be `silent-success` inverted: work nobody
// asked for. So we render honest verbs, ORDERED BY WHAT ACTUALLY WORKS ON AN EMPTY BOOK:
//
//   1. "Start with your first arc" — the STRUCTURE ORIGIN (spec 2026-07-17-studio-structure-origin).
//      The ONLY verb that works with zero data. Creates the arc (book-scoped `structure_node`, no
//      Work needed) and ensures the Work + KG project alongside. This is the PRIMARY.
//   2. "Extract the plan from the manuscript" — the SC6 decompiler (`materialize-scenes`). It is
//      DETERMINISTIC and $0 (no LLM), so it is a direct EDIT-gated call, not a priced confirm card.
//      It mints one spec node per PARSED SCENE (plus their chapters). It does NOT group them into
//      arcs — that is the separate LLM step (`composition_arc_import_analyze`), a Tier-W MCP tool by
//      design (agentic logic goes through the agent, never a bespoke HTTP endpoint). So we say so,
//      and the extracted chapters land in the "unassigned" strip until an arc pass runs.
//   3. "Paste a plan you've already written" — opens the `planner` (PlanForge) panel.
//
// ⚠ HISTORY — why the order and the labels changed (docs/bugs/2026-07-17-studio-first-use-cold-start):
// this file used to say "Neither is a dead button (PH7's visible-fallback): both are live today."
// That was FALSE in the exact state this component exists to serve. On a NEW book BOTH were dead:
// Extract reads scenes already parsed from chapters (there are none), and "Plan from scratch" was
// never from scratch — it opens the Planner, whose Propose is hard-gated on a pre-written braindump
// (PlannerPanel.tsx:120 `effectiveMarkdown.trim().length > 0`). Extract was also the `bg-primary` —
// the one guaranteed to fail on a new book. Together with the never-wired Manuscript `+`, that made
// the Studio a closed loop with no origin: nothing in it created the first thing.
//
// PH7 (visible-fallback) is honoured for real now: Extract renders DISABLED WITH ITS REASON when the
// book has no chapters — a fact we can prove upfront from `useBookChapters` — rather than letting the
// user discover it by clicking. The finer case (chapters exist but no scenes are parsed) is NOT
// knowable before the call — `scenes_total` only comes back in the decompiler's response — so it
// stays post-hoc via `nothingParsed`. We do not invent a read surface to gold-plate that tier.
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

export interface PlanEmptyStateProps {
  /** The origin: create the book's first arc. Null ⇒ the caller can't offer it (no EDIT / no token). */
  onStartArc: ((title: string) => void) | null;
  creatingArc: boolean;
  arcError: string | null;
  /** Runs the decompiler. Null ⇒ the caller can't offer it (no EDIT grant / no token). */
  onExtract: (() => void) | null;
  /** PH7: proven upfront from useBookChapters. 0 chapters ⇒ Extract cannot do anything. */
  hasChapters: boolean;
  onPlanFromScratch: () => void;
  extracting: boolean;
  /** The decompiler's own report — surfaced verbatim, never swallowed. */
  result: { scenes_total: number; created: number; chapters: number; detail: string | null } | null;
  error: string | null;
}

export function PlanEmptyState({
  onStartArc,
  creatingArc,
  arcError,
  onExtract,
  hasChapters,
  onPlanFromScratch,
  extracting,
  result,
  error,
}: PlanEmptyStateProps) {
  const { t } = useTranslation('studio');
  const [title, setTitle] = useState('');

  // A 200 that materialised NOTHING is not a success to celebrate — it means the manuscript has no
  // PARSED scenes yet (the decompiler reads book-service's parse leaves). Saying "done!" over zero
  // work is the silent-success bug class; name the actual next step instead.
  const nothingToExtract = result != null && result.scenes_total === 0;

  return (
    <div
      data-testid="plan-hub-empty"
      className="flex h-full w-full flex-col items-center justify-center gap-4 p-8 text-center"
    >
      <div className="max-w-md space-y-1">
        <h2 className="text-base font-semibold">
          {t('planHub.empty.title', 'No plan for this book yet')}
        </h2>
        <p className="text-sm text-muted-foreground">
          {t(
            'planHub.empty.body',
            'The Plan Hub shows the spec — arcs, chapters, scenes. This book has none yet. It will never be invented from your manuscript: extract it, or write one.',
          )}
        </p>
      </div>

      {/* 1 — THE ORIGIN. Primary, and the only verb that works with zero data. Inline-named: a modal
          would take the writer off the canvas to talk about the canvas. ↵ with an empty field is
          allowed — an untitled arc they rename in place beats a form that blocks the first step. */}
      {onStartArc && (
        <form
          className="flex w-full max-w-md flex-col items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (creatingArc) return;
            onStartArc(title.trim() || t('planHub.empty.untitledArc', 'Untitled arc'));
            setTitle('');
          }}
        >
          <div className="flex w-full items-center gap-2">
            <input
              data-testid="plan-hub-arc-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              disabled={creatingArc}
              placeholder={t('planHub.empty.arcPlaceholder', 'Name your first arc…')}
              className="min-w-0 flex-1 rounded-md border bg-background px-3 py-1.5 text-sm disabled:opacity-50"
            />
            <button
              type="submit"
              data-testid="plan-hub-start-arc-cta"
              disabled={creatingArc}
              className="shrink-0 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground disabled:opacity-50"
            >
              {creatingArc
                ? t('planHub.empty.startingArc', 'Creating…')
                : t('planHub.empty.startArcCta', 'Start with your first arc')}
            </button>
          </div>
          {arcError && (
            <p data-testid="plan-hub-arc-error" className="text-xs text-destructive">
              {arcError}
            </p>
          )}
        </form>
      )}

      <div className="flex flex-col items-center gap-1">
        <div className="flex flex-wrap items-center justify-center gap-2">
          {/* 2 — Extract. PH7: disabled WITH ITS REASON when we can prove it's useless (0 chapters). */}
          <button
            type="button"
            data-testid="plan-hub-extract-cta"
            disabled={!onExtract || extracting || !hasChapters}
            onClick={() => onExtract?.()}
            className="rounded-md border px-3 py-1.5 text-sm font-medium hover:bg-accent disabled:opacity-50 disabled:hover:bg-transparent"
          >
            {extracting
              ? t('planHub.empty.extracting', 'Extracting…')
              : t('planHub.empty.extractCta', 'Extract the plan from the manuscript')}
          </button>
          {/* 3 — relabelled. It opens the Planner, which CANNOT start from nothing: its Propose is
              gated on a pre-written novel-system markdown. The old "Plan from scratch" promised the
              one thing it can't do. */}
          <button
            type="button"
            data-testid="plan-hub-plan-cta"
            onClick={onPlanFromScratch}
            className="rounded-md border px-3 py-1.5 text-sm font-medium hover:bg-accent"
          >
            {t('planHub.empty.planCta', "Paste a plan you've already written")}
          </button>
        </div>
        {!hasChapters && (
          <p data-testid="plan-hub-extract-blocked" className="text-xs text-muted-foreground">
            {t('planHub.empty.extractNeedsChapters', 'Extracting needs chapters — this book has none yet.')}
          </p>
        )}
      </div>

      <p className="max-w-md text-xs text-muted-foreground">
        {t(
          'planHub.empty.extractNote',
          'Extracting reads the scenes already parsed from your chapters and turns each into a spec node. Grouping them into arcs is a separate AI step — ask the agent for it. Until then the extracted chapters sit in the “Unassigned” strip.',
        )}
      </p>

      {error && (
        <p data-testid="plan-hub-extract-error" className="text-xs text-destructive">
          {error}
        </p>
      )}

      {nothingToExtract && !error && (
        <p data-testid="plan-hub-extract-empty" className="max-w-md text-xs text-amber-600">
          {t(
            'planHub.empty.nothingParsed',
            'Nothing to extract — this book has no parsed scenes yet. Parse or import the chapters first, then extract.',
          )}
        </p>
      )}
    </div>
  );
}
