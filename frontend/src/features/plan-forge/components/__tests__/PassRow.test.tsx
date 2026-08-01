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


// ── the door to the editors ─────────────────────────────────────────────────────────────────────
// `awaitingReview` (blocking + completed + pending) was the ONLY route to CheckpointReview, which
// is the only host of the structured editors. That made the four ADVISORY atoms — motifs, world,
// character_arcs, scenes — uneditable in the running app however complete their editors were, and
// made cast/beats uneditable the moment they were approved. Caught by a live browser pass, not by
// any unit test, because the editor tests render CheckpointReview directly with a fabricated pass.

describe('PassRow — the edit door', () => {
  const row = (over: Partial<PlanPass>, onReview: (id: string) => void = noop) => (
    <PassRow index={1} pass={pass(over)} blockedAtHere={false} onRun={noop} onReview={onReview} disabled={false} />
  );

  it('an ADVISORY completed pass offers an edit door', () => {
    render(row({ pass_id: 'motifs', checkpoint: 'advisory', output_kind: 'motif_plan',
                 status: 'completed', decision: 'auto', artifact_id: 'art1' }));
    expect(screen.getByTestId('pass-edit-motifs')).toBeInTheDocument();
  });

  it('an ACCEPTED blocking pass is still re-openable (no one-way door)', () => {
    render(row({ pass_id: 'cast', checkpoint: 'blocking', output_kind: 'cast_plan',
                 status: 'completed', decision: 'accepted', artifact_id: 'art1' }));
    expect(screen.getByTestId('pass-edit-cast')).toBeInTheDocument();
  });

  it('a pass that never ran has nothing to open', () => {
    render(row({ pass_id: 'self_heal', checkpoint: 'advisory', output_kind: 'scene_plan',
                 status: 'pending', decision: 'pending', artifact_id: null }));
    expect(screen.queryByTestId('pass-edit-self_heal')).toBeNull();
  });

  it('a completed pass with NO artifact offers no door (nothing to show)', () => {
    render(row({ pass_id: 'world', checkpoint: 'advisory', output_kind: 'world_plan',
                 status: 'completed', decision: 'auto', artifact_id: null }));
    expect(screen.queryByTestId('pass-edit-world')).toBeNull();
  });

  it('the edit door opens the SAME review host the blocking CTA uses', () => {
    const onReview = vi.fn();
    render(row({ pass_id: 'scenes', checkpoint: 'advisory', output_kind: 'scene_plan',
                 status: 'completed', decision: 'auto', artifact_id: 'art1' }, onReview));
    fireEvent.click(screen.getByTestId('pass-edit-scenes'));
    expect(onReview).toHaveBeenCalledWith('scenes');
  });
});

// ── blocked ≠ unreadable (found by driving the real rail) ─────────────────────
// F10 one step over. `blocked` means this pass cannot be RE-RUN yet — its upstream is stale or
// unaccepted. It never meant the artifact the pass already produced is unreadable. But the action
// cell was `running ? … : awaitingReview ? … : blocked ? <lock/> : (edit… + re-run)`, so the lock
// swallowed the door entirely.
//
// The trigger is an ordinary authoring action, not an edge case: edit `beats`, and
// `character_arcs`/`scenes`/`self_heal` — all completed, all still holding artifacts — went
// doorless. The author lost the ability to even LOOK at the scene plan they were working from.

describe('PassRow — a blocked pass keeps the door to what it already produced', () => {
  it('blocked + completed + has artifact → the edit door is STILL there, beside the lock', () => {
    render(<PassRow index={5} {...base} pass={pass({
      pass_id: 'character_arcs', checkpoint: 'advisory', status: 'completed', decision: 'auto',
      fresh: false, blockers: ['beats'], artifact_id: 'a1',
    })} />);
    expect(screen.getByTestId('pass-blocked-character_arcs')).toBeTruthy();  // still says why
    expect(screen.getByTestId('pass-edit-character_arcs')).toBeTruthy();     // …and still opens
  });

  it('blocked with NOTHING produced yet offers no door — there is nothing to read', () => {
    render(<PassRow index={6} {...base} pass={pass({
      pass_id: 'scenes', checkpoint: 'advisory', status: null, decision: null,
      fresh: false, blockers: ['beats'], artifact_id: null,
    })} />);
    expect(screen.getByTestId('pass-blocked-scenes')).toBeTruthy();
    expect(screen.queryByTestId('pass-edit-scenes')).toBeNull();
  });
});
