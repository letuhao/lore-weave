// #19 G11 — a custom step renderer (react-joyride's default tooltip isn't fully accessible out
// of the box per 2026 tour-library benchmarks). Bypasses joyride's own Back/Next/Skip action
// dispatch entirely — the parent only ever renders ONE step at a time (see useStudioTour), so
// these buttons call the hook's own next/prev/stop directly instead of joyride's internal state.
import { useEffect, useRef } from 'react';
import type { TooltipRenderProps } from 'react-joyride';

interface Props extends TooltipRenderProps {
  stepIndex: number;
  stepCount: number;
  onNext: () => void;
  onPrev: () => void;
  onSkip: () => void;
}

export function StudioTourTooltip({ step, stepIndex, stepCount, onNext, onPrev, onSkip, tooltipProps }: Props) {
  const nextRef = useRef<HTMLButtonElement>(null);
  const isLast = stepIndex + 1 >= stepCount;

  // Focus management (G11): move focus to the primary action whenever a new step mounts.
  useEffect(() => { nextRef.current?.focus(); }, [stepIndex]);

  // Esc-to-skip (G11) — joyride's own overlay-click handling is intentionally not relied on
  // (this component owns navigation fully); Esc is the one dismiss path guaranteed to always work.
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => { if (e.key === 'Escape') onSkip(); };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onSkip]);

  return (
    <div
      {...tooltipProps}
      role="dialog"
      aria-label={typeof step.title === 'string' ? step.title : undefined}
      data-testid="studio-tour-tooltip"
      className="max-w-xs rounded-lg border bg-background p-4 shadow-xl"
    >
      <div aria-live="polite">
        <div className="text-sm font-semibold text-foreground">{step.title}</div>
        <div className="mt-1 text-xs text-muted-foreground">{step.content}</div>
      </div>
      <div className="mt-3 flex items-center justify-between gap-2">
        <button
          type="button"
          data-testid="studio-tour-skip"
          onClick={onSkip}
          className="rounded text-xs text-muted-foreground transition-colors hover:text-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
        >
          Skip tour
        </button>
        <div className="flex gap-2">
          {stepIndex > 0 && (
            <button
              type="button"
              data-testid="studio-tour-back"
              onClick={onPrev}
              className="rounded border px-2 py-1 text-xs transition-colors hover:bg-secondary focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
            >
              Back
            </button>
          )}
          <button
            ref={nextRef}
            type="button"
            data-testid="studio-tour-next"
            onClick={onNext}
            className="rounded bg-primary px-2 py-1 text-xs text-primary-foreground transition-colors hover:bg-primary/90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            {isLast ? 'Done' : `Next (${stepIndex + 1}/${stepCount})`}
          </button>
        </div>
      </div>
    </div>
  );
}
