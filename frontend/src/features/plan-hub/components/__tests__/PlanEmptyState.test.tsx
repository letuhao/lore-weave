// 24 PH21 — the empty state. Two honest verbs, and NEITHER is a dead button.
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { PlanEmptyState } from '../PlanEmptyState';

const props = {
  onExtract: vi.fn(),
  onPlanFromScratch: vi.fn(),
  extracting: false,
  result: null,
  error: null,
};

describe('PlanEmptyState (PH21)', () => {
  it('offers exactly the two CTAs, both live', () => {
    render(<PlanEmptyState {...props} />);
    const extract = screen.getByTestId('plan-hub-extract-cta') as HTMLButtonElement;
    const plan = screen.getByTestId('plan-hub-plan-cta') as HTMLButtonElement;
    expect(extract.disabled).toBe(false); // the /v1 materialize-scenes mirror EXISTS (OQ-9 closed)
    expect(plan.disabled).toBe(false);
  });

  it('runs the decompiler / opens the planner', () => {
    const onExtract = vi.fn();
    const onPlan = vi.fn();
    render(<PlanEmptyState {...props} onExtract={onExtract} onPlanFromScratch={onPlan} />);
    fireEvent.click(screen.getByTestId('plan-hub-extract-cta'));
    fireEvent.click(screen.getByTestId('plan-hub-plan-cta'));
    expect(onExtract).toHaveBeenCalled();
    expect(onPlan).toHaveBeenCalled();
  });

  it('disables extract while it runs (no double-decompile)', () => {
    render(<PlanEmptyState {...props} extracting />);
    expect((screen.getByTestId('plan-hub-extract-cta') as HTMLButtonElement).disabled).toBe(true);
  });

  it('a 200 that extracted NOTHING says so — it is not a success', () => {
    // The decompiler reads book-service's PARSE LEAVES. Zero leaves ⇒ zero spec nodes. Reporting
    // "extracted!" over zero work is the silent-success bug class; name the real next step.
    render(
      <PlanEmptyState
        {...props}
        result={{ scenes_total: 0, created: 0, chapters: 0, detail: null }}
      />,
    );
    expect(screen.getByTestId('plan-hub-extract-empty')).toBeTruthy();
  });

  it('a real extraction does NOT show the nothing-to-extract notice', () => {
    render(
      <PlanEmptyState
        {...props}
        result={{ scenes_total: 12, created: 12, chapters: 3, detail: null }}
      />,
    );
    expect(screen.queryByTestId('plan-hub-extract-empty')).toBeNull();
  });

  it('surfaces an extraction failure', () => {
    render(<PlanEmptyState {...props} error="boom" />);
    expect(screen.getByTestId('plan-hub-extract-error').textContent).toContain('boom');
  });

  it('cannot offer extraction with no handler (no EDIT grant) — visible, disabled, never dead', () => {
    render(<PlanEmptyState {...props} onExtract={null} />);
    expect((screen.getByTestId('plan-hub-extract-cta') as HTMLButtonElement).disabled).toBe(true);
  });
});
