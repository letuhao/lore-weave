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
