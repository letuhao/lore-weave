import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { QualityReport } from '../../api';
import { QualityReportSection } from '../QualityReportSection';

// Pure view over useQualityReport — mock the controller and assert wiring + rendering.
const state = vi.hoisted(() => ({ value: {} as Record<string, unknown> }));
vi.mock('../../hooks/useQualityReport', () => ({
  useQualityReport: () => state.value,
}));

function base(over: Record<string, unknown> = {}) {
  return { report: null as QualityReport | null, loading: false, error: null, ran: false, run: vi.fn(), ...over };
}

const render_ = (modelRef = 'm') =>
  render(<QualityReportSection projectId="p" chapterId="c" token="t" modelRef={modelRef} />);

const fullReport: QualityReport = {
  critic: { coherence: 4, voice_match: 3, pacing: 5, canon_consistency: 2, violations: [{ rule_id: 'R1', violated: true, span: 'he said', why: 'wrong pronoun' }] },
  promises: { introduced: ['a', 'b'], resolved: ['a'], dropped: ['b'], introduced_count: 2, resolved_count: 1, dropped_count: 1, dropped_rate: 0.5 },
};

describe('QualityReportSection', () => {
  it('runs the analysis on click', () => {
    const run = vi.fn();
    state.value = base({ run });
    render_();
    fireEvent.click(screen.getByTestId('quality-run'));
    expect(run).toHaveBeenCalled();
  });

  it('disables the button with no model', () => {
    state.value = base();
    render_('');
    expect((screen.getByTestId('quality-run') as HTMLButtonElement).disabled).toBe(true);
  });

  // NOTE: the global react-i18next mock returns KEYS (with interpolation), not English
  // defaultValues — repo test convention. So translated labels assert on keys; data on values.
  it('renders critic dims, violations and dropped promises', () => {
    state.value = base({ report: fullReport, ran: true });
    render_();
    expect(screen.getByTestId('quality-critic').textContent).toContain('4/5');       // data
    expect(screen.getByTestId('quality-violations').textContent).toContain('wrong pronoun'); // data
    expect(screen.getByTestId('quality-promises').textContent).toContain('b');        // dropped promise (data)
  });

  it('shows a clean state when nothing is dropped', () => {
    state.value = base({
      ran: true,
      report: { ...fullReport, promises: { ...fullReport.promises, dropped: [], dropped_count: 0 } },
    });
    render_();
    expect(screen.getByTestId('quality-promises').textContent).toContain('qualityNoDrop');
  });

  it('shows a hint when the promise audit is unavailable (not silent)', () => {
    state.value = base({
      ran: true,
      report: { ...fullReport, promises: { ...fullReport.promises, error: 'audit_error' } },
    });
    render_();
    expect(screen.getByTestId('quality-promises-na')).toBeTruthy();
    expect(screen.queryByTestId('quality-promises')).toBeNull();
  });

  it('degrades gracefully when the critic is unavailable', () => {
    state.value = base({
      ran: true,
      report: { ...fullReport, critic: { coherence: null, voice_match: null, pacing: null, canon_consistency: null, violations: [], error: 'critic_unavailable' } },
    });
    render_();
    expect(screen.getByTestId('quality-critic').textContent).toContain('qualityCriticNa');
  });
});
