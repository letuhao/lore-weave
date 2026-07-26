import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { PassRow } from '../PassRow';
import type { PlanPass } from '../../types';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (_k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? _k }),
}));

function pass(over: Partial<PlanPass>): PlanPass {
  return {
    pass_id: 'beats', checkpoint: 'blocking', output_kind: 'beat_plan', depends_on: ['motifs'],
    status: 'pending', decision: 'pending', artifact_id: null, job_id: null,
    fresh: false, blockers: [], ...over,
  };
}

const noop = () => {};
const base = { blockedAtHere: false, onRun: noop, onReview: noop, onView: noop, disabled: false };

describe('PassRow — the action cell reflects the pass state', () => {
  it('runnable (no blockers, not run) → a run button', () => {
    render(<PassRow index={4} pass={pass({})} blockedAtHere={false} onRun={noop} onReview={noop} disabled={false} />);
    expect(screen.getByTestId('pass-run-beats')).toBeInTheDocument();
    expect(screen.queryByTestId('pass-blocked-beats')).toBeNull();
  });

  it('blocked (upstream stale/unaccepted) → a blocked indicator, NOT a run button', () => {
    render(<PassRow index={3} pass={pass({ pass_id: 'world', checkpoint: 'advisory', blockers: ['cast'] })}
      blockedAtHere={false} onRun={noop} onReview={noop} disabled={false} />);
    expect(screen.getByTestId('pass-blocked-world')).toBeInTheDocument();
    expect(screen.queryByTestId('pass-run-world')).toBeNull();
  });

  it('blocking + completed + decision pending → a review affordance', () => {
    const onReview = vi.fn();
    render(<PassRow index={2} pass={pass({ pass_id: 'cast', status: 'completed', decision: 'pending', fresh: true })}
      blockedAtHere onRun={noop} onReview={onReview} disabled={false} />);
    const btn = screen.getByTestId('pass-review-cast');
    fireEvent.click(btn);
    expect(onReview).toHaveBeenCalledWith('cast');
  });

  it('running → a spinner, no run/blocked/review action', () => {
    render(<PassRow index={4} pass={pass({ status: 'running', job_id: 'j1' })}
      blockedAtHere={false} onRun={noop} onReview={noop} disabled />);
    expect(screen.getByTestId('pass-status-beats').textContent).toContain('running');
    expect(screen.queryByTestId('pass-run-beats')).toBeNull();
    expect(screen.queryByTestId('pass-review-beats')).toBeNull();
  });

  it('completed + fresh → freshness reads "fresh"; a completed pass offers re-run', () => {
    render(<PassRow index={1} pass={pass({ pass_id: 'motifs', checkpoint: 'advisory', status: 'completed', decision: 'auto', fresh: true })}
      blockedAtHere={false} onRun={noop} onReview={noop} disabled={false} />);
    expect(screen.getByTestId('pass-fresh-motifs').textContent).toContain('fresh');
    expect(screen.getByTestId('pass-run-motifs').textContent).toContain('re-run');
  });

  it('completed + stale → freshness reads "stale"', () => {
    render(<PassRow index={1} pass={pass({ pass_id: 'motifs', checkpoint: 'advisory', status: 'completed', decision: 'auto', fresh: false })}
      blockedAtHere={false} onRun={noop} onReview={noop} onView={noop} disabled={false} />);
    expect(screen.getByTestId('pass-fresh-motifs').textContent).toContain('stale');
  });

  it('PS-9 — a completed pass with an artifact opens it read-only (was unreachable)', () => {
    const onView = vi.fn();
    render(<PassRow index={1} pass={pass({ pass_id: 'motifs', checkpoint: 'advisory', status: 'completed', decision: 'auto', fresh: true, artifact_id: 'art9' })}
      {...base} onView={onView} />);
    fireEvent.click(screen.getByTestId('pass-view-motifs'));
    expect(onView).toHaveBeenCalledWith('art9');
  });

  it('a NOT-run pass offers no view (nothing to read yet)', () => {
    render(<PassRow index={4} pass={pass({ artifact_id: null })} {...base} />);
    expect(screen.queryByTestId('pass-view-beats')).toBeNull();
  });
});
