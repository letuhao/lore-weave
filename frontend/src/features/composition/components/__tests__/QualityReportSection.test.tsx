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
  threads: { raised: ['thread-a', 'thread-b'], resolved: ['thread-a'], raised_count: 2, resolved_count: 1 },
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
  it('renders critic dims, violations and the threads raised (informational, not a defect)', () => {
    state.value = base({ report: fullReport, ran: true });
    render_();
    expect(screen.getByTestId('quality-critic').textContent).toContain('4/5');       // data
    expect(screen.getByTestId('quality-violations').textContent).toContain('wrong pronoun'); // data
    const threads = screen.getByTestId('quality-threads');
    expect(threads.textContent).toContain('thread-b');        // raised thread (data)
    expect(threads.textContent).toContain('qualityThreadsRaised'); // neutral "raised" label, not "dropped"
    expect(threads.textContent).not.toContain('dropped');     // the false-positive alarm is gone
  });

  it('shows a clean state when no threads are raised', () => {
    state.value = base({
      ran: true,
      report: { ...fullReport, threads: { ...fullReport.threads, raised: [], raised_count: 0 } },
    });
    render_();
    expect(screen.getByTestId('quality-threads').textContent).toContain('qualityNoThreads');
  });

  it('shows a hint when the thread audit is unavailable (not silent)', () => {
    state.value = base({
      ran: true,
      report: { ...fullReport, threads: { ...fullReport.threads, error: 'audit_error' } },
    });
    render_();
    expect(screen.getByTestId('quality-threads-na')).toBeTruthy();
    expect(screen.queryByTestId('quality-threads')).toBeNull();
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
