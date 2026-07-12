// 24 PH21 — the empty state: this book has NO spec at all (no arcs, no chapter nodes).
//
// The Hub NEVER synthesises a graph from the manuscript's chapters. Inferring structure is the
// DECOMPILER's explicit job, and doing it uninvited would be `silent-success` inverted: work nobody
// asked for. So we render exactly two honest verbs:
//
//   1. "Extract the plan from the manuscript" — the SC6 decompiler (`materialize-scenes`). It is
//      DETERMINISTIC and $0 (no LLM), so it is a direct EDIT-gated call, not a priced confirm card.
//      It mints one spec node per PARSED SCENE (plus their chapters). It does NOT group them into
//      arcs — that is the separate LLM step (`composition_arc_import_analyze`), a Tier-W MCP tool by
//      design (agentic logic goes through the agent, never a bespoke HTTP endpoint). So we say so,
//      and the extracted chapters land in the "unassigned" strip until an arc pass runs.
//   2. "Plan from scratch" — opens the `planner` (PlanForge) panel.
//
// Neither is a dead button (PH7's visible-fallback): both are live today.
import { useTranslation } from 'react-i18next';

export interface PlanEmptyStateProps {
  /** Runs the decompiler. Null ⇒ the caller can't offer it (no EDIT grant / no token). */
  onExtract: (() => void) | null;
  onPlanFromScratch: () => void;
  extracting: boolean;
  /** The decompiler's own report — surfaced verbatim, never swallowed. */
  result: { scenes_total: number; created: number; chapters: number; detail: string | null } | null;
  error: string | null;
}

export function PlanEmptyState({
  onExtract,
  onPlanFromScratch,
  extracting,
  result,
  error,
}: PlanEmptyStateProps) {
  const { t } = useTranslation('studio');

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

      <div className="flex flex-wrap items-center justify-center gap-2">
        <button
          type="button"
          data-testid="plan-hub-extract-cta"
          disabled={!onExtract || extracting}
          onClick={() => onExtract?.()}
          className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground disabled:opacity-50"
        >
          {extracting
            ? t('planHub.empty.extracting', 'Extracting…')
            : t('planHub.empty.extractCta', 'Extract the plan from the manuscript')}
        </button>
        <button
          type="button"
          data-testid="plan-hub-plan-cta"
          onClick={onPlanFromScratch}
          className="rounded-md border px-3 py-1.5 text-sm font-medium hover:bg-accent"
        >
          {t('planHub.empty.planCta', 'Plan from scratch')}
        </button>
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
