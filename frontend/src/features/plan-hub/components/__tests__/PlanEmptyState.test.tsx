// 24 PH21 — the empty state. Honest verbs, ordered by what actually works on an EMPTY book.
//
// ⚠ This file used to open "Two honest verbs, and NEITHER is a dead button" and assert
// `extract.disabled === false` unconditionally. Both were wrong in the state this component exists
// to serve: on a NEW book Extract has no parsed scenes to read and "Plan from scratch" opens a
// Planner that hard-gates on a pre-written braindump — so BOTH verbs were dead, and the Studio had
// no origin at all (docs/bugs/2026-07-17-studio-first-use-cold-start.md).
// The origin verb + the PH7-for-real disabled-with-reason tier are asserted below.
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { PlanEmptyState } from '../PlanEmptyState';

const props = {
  onStartArc: vi.fn(),
  creatingArc: false,
  arcError: null,
  onExtract: vi.fn(),
  hasChapters: true,
  onPlanFromScratch: vi.fn(),
  extracting: false,
  result: null,
  error: null,
};

describe('PlanEmptyState (PH21)', () => {
  // ── the ORIGIN — the whole point of this component ─────────────────────────
  it('offers the origin verb ENABLED with zero data — the exit from the dead loop', () => {
    render(<PlanEmptyState {...props} hasChapters={false} />);
    const start = screen.getByTestId('plan-hub-start-arc-cta') as HTMLButtonElement;
    expect(start.disabled).toBe(false); // works on an empty book: an arc needs no Work, no chapters
  });

  it('creates the first arc with the typed title', () => {
    const onStartArc = vi.fn();
    render(<PlanEmptyState {...props} onStartArc={onStartArc} />);
    fireEvent.change(screen.getByTestId('plan-hub-arc-title'), { target: { value: "Vesna's debt" } });
    fireEvent.click(screen.getByTestId('plan-hub-start-arc-cta'));
    expect(onStartArc).toHaveBeenCalledWith("Vesna's debt");
  });

  it('an empty title still creates — a naming form must never block the first step', () => {
    const onStartArc = vi.fn();
    render(<PlanEmptyState {...props} onStartArc={onStartArc} />);
    fireEvent.click(screen.getByTestId('plan-hub-start-arc-cta'));
    expect(onStartArc).toHaveBeenCalledOnce();
    expect(onStartArc.mock.calls[0][0]).toBeTruthy(); // falls back to a default, never ''
  });

  it('disables the origin while it runs (no double-create)', () => {
    render(<PlanEmptyState {...props} creatingArc />);
    expect((screen.getByTestId('plan-hub-start-arc-cta') as HTMLButtonElement).disabled).toBe(true);
  });

  it('surfaces an arc-create failure', () => {
    render(<PlanEmptyState {...props} arcError="boom" />);
    expect(screen.getByTestId('plan-hub-arc-error').textContent).toContain('boom');
  });

  it('hides the origin when the caller cannot offer it (no EDIT grant / no token)', () => {
    render(<PlanEmptyState {...props} onStartArc={null} />);
    expect(screen.queryByTestId('plan-hub-start-arc-cta')).toBeNull();
  });

  // ── PH7, for real: disabled WITH a reason, proven upfront ──────────────────
  it('disables Extract with a visible reason when the book has no chapters', () => {
    render(<PlanEmptyState {...props} hasChapters={false} />);
    expect((screen.getByTestId('plan-hub-extract-cta') as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByTestId('plan-hub-extract-blocked')).toBeTruthy();
  });

  it('enables Extract once chapters exist (the no-parsed-scenes tier stays post-hoc)', () => {
    render(<PlanEmptyState {...props} hasChapters />);
    expect((screen.getByTestId('plan-hub-extract-cta') as HTMLButtonElement).disabled).toBe(false);
    expect(screen.queryByTestId('plan-hub-extract-blocked')).toBeNull();
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
    render(<PlanEmptyState {...props} result={{ scenes_total: 0, created: 0, chapters: 0, detail: null }} />);
    expect(screen.getByTestId('plan-hub-extract-empty')).toBeTruthy();
  });

  it('a real extraction does NOT show the nothing-to-extract notice', () => {
    render(<PlanEmptyState {...props} result={{ scenes_total: 12, created: 12, chapters: 3, detail: null }} />);
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
