import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { PromiseCoverage } from '../../api';
import { BookPromiseCoverageSection } from '../BookPromiseCoverageSection';

// Pure view over useBookPromiseCoverage — mock the controller and assert wiring + rendering.
const state = vi.hoisted(() => ({ value: {} as Record<string, unknown> }));
vi.mock('../../hooks/useBookPromiseCoverage', () => ({
  useBookPromiseCoverage: () => state.value,
}));

function base(over: Record<string, unknown> = {}) {
  return { coverage: null as PromiseCoverage | null, chapters: null, loading: false, error: null, ran: false, run: vi.fn(), ...over };
}

const render_ = (modelRef = 'm') =>
  render(<BookPromiseCoverageSection projectId="p" token="t" modelRef={modelRef} />);

const full: PromiseCoverage = {
  coverage: [
    { promise: 'the sealed grimoire', verdict: 'paid' },
    { promise: 'the debt to the sect', verdict: 'abandoned' },
    { promise: 'the missing brother', verdict: 'progressing' },
  ],
  tracked_count: 3, introduced_count: 3, paid_count: 1, progressing_count: 1,
  abandoned_count: 1, absent_count: 0, pay_rate: 0.33, sustained_rate: 0.66, abandon_rate: 0.33,
};

describe('BookPromiseCoverageSection', () => {
  it('runs the whole-book analysis on click', () => {
    const run = vi.fn();
    state.value = base({ run });
    render_();
    fireEvent.click(screen.getByTestId('coverage-run'));
    expect(run).toHaveBeenCalled();
  });

  it('disables the button with no model', () => {
    state.value = base();
    render_('');
    expect((screen.getByTestId('coverage-run') as HTMLButtonElement).disabled).toBe(true);
  });

  // T10 — the job already carries a machine-readable reason; the panel used to branch on it and
  // then render one fixed string for every cause. So "you have not declared any promises yet"
  // (one click to fix) and "the extraction call failed" (not the user's to fix) read identically.
  describe('T10 — the reason is rendered, not discarded', () => {
    const withError = (error: string) =>
      state.value = base({ coverage: { ...full, coverage: [], tracked_count: 0, error } });

    it('tells an unconfigured user apart from a broken one', () => {
      // The i18n test harness renders KEYS rather than defaultValue, so assert the property that
      // actually matters and is harness-independent: the two causes must not produce the same
      // output. Rendering one fixed string for every cause WAS the defect.
      withError('no_tracked_promises');
      const { unmount } = render_();
      const unconfigured = screen.getByTestId('coverage-na');
      expect(unconfigured.getAttribute('data-reason')).toBe('no_tracked_promises');
      const unconfiguredText = unconfigured.textContent;
      unmount();

      withError('promise_extraction_failed');
      render_();
      const failed = screen.getByTestId('coverage-na');
      expect(failed.getAttribute('data-reason')).toBe('promise_extraction_failed');
      expect(failed.textContent).not.toBe(unconfiguredText);
      // …and a genuine failure is styled as one, not as neutral "nothing here yet" grey.
      expect(failed.className).toMatch(/amber/);
    });

    it('falls back for an unmapped code rather than rendering blank, and logs it', () => {
      const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
      withError('some_future_code');
      render_();
      const el = screen.getByTestId('coverage-na');
      expect(el.textContent?.trim().length).toBeGreaterThan(0);
      expect(warn).toHaveBeenCalled();
      warn.mockRestore();
    });

    it('renders no reason at all when coverage succeeded (NV-7)', () => {
      state.value = base({ coverage: full });
      render_();
      expect(screen.queryByTestId('coverage-na')).toBeNull();
    });
  });

  it('renders count chips and calls out abandoned promises', () => {
    // NOTE: the global i18n mock returns KEYS (count values live in ignored defaultValue
    // interpolation) — assert the chip keys are present + the abandoned promise data.
    state.value = base({ coverage: full, ran: true });
    render_();
    expect(screen.getByTestId('coverage-counts').textContent).toContain('coverageAbandoned');
    const body = screen.getByTestId('coverage-body');
    expect(body.textContent).toContain('the debt to the sect');  // the abandoned promise (data)
    expect(body.textContent).not.toContain('the sealed grimoire'); // paid ones not in the drop list
  });

  it('shows a clean state when nothing is abandoned', () => {
    state.value = base({
      ran: true,
      coverage: { ...full, coverage: full.coverage.filter((p) => p.verdict !== 'abandoned'), abandoned_count: 0 },
    });
    render_();
    expect(screen.getByTestId('coverage-body').textContent).toContain('coverageClean');
  });

  it('degrades gracefully when coverage is unavailable', () => {
    state.value = base({ ran: true, coverage: { ...full, error: 'coverage_error' } });
    render_();
    expect(screen.getByTestId('coverage-na')).toBeTruthy();
    expect(screen.queryByTestId('coverage-body')).toBeNull();
  });
});
